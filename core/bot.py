import ast
import asyncio
import importlib
import inspect
import json
import logging
import logging.handlers
import os
import random
import string
import traceback
from datetime import datetime
from textwrap import indent
from types import ModuleType
from typing import Callable, Dict, List, Literal, Optional

import aiohttp
import discord
import humanfriendly
import mystbin
from discord.ext import commands, ipc, tasks
from discord.ext.commands import Greedy
from expiringdict import ExpiringDict
from playwright.async_api import async_playwright
from playwright.async_api._generated import Browser

import config
from modules.context import Context
from modules.util.converters import ascii_list
from modules.util.documentation.parser import DocParser
from modules.util.handlers.nginx import NginxHandler


class amyrin(commands.Bot):
    def __init__(self, *args, **kwargs) -> commands.Bot:
        super().__init__(command_prefix=self._get_prefix(), *args, **kwargs)
        self.uptime = datetime.utcnow()
        self.myst = mystbin.Client(token=config.MYSTBIN_API)

        self.debug = config.DEBUG

        self.owner_id = config.OWNERS[0]
        self.owner_ids = config.OWNERS
        self.session = (
            None  # aiohttp.ClientSession instance, later defined in self.setup_hook
        )
        self.logger = None  # logging.Logger instance, later defined in self.startup
        self.expr_states = {}  # expr.py states, in use in modules.util.views.calculator

        self.playwright = None  # playwright instance, later defined in self.setup_hook
        self.browser: Browser = (
            None  # playwright chromium instance, later defined in self.setup_hook
        )
        self.docparser: DocParser = None  # DocParser instance, later defined in modules.util.documentation.parser

        self.ipc = ipc.Server(self, host="0.0.0.0", secret_key=config.IPC_SECRET_KEY)

        self.color = (
            0x2F3136  # color used for embeds and whereever else it would be appropiate
        )

        self.nginx = NginxHandler(url=config.Nginx.url, path=config.Nginx.path)

        self.command_tasks: Dict[str, dict] = {}
        self.command_cache: Dict[int, List[discord.Message]] = ExpiringDict(
            max_len=1000, max_age_seconds=60
        )

        self.context = Context

        self.module_relatives: Dict[str, List[str]] = {}

    @tasks.loop(minutes=30)
    async def pfp_rotation(self):
        if config.DEBUG:
            return

        await self.wait_until_ready()

        root = os.getcwd()
        path = os.path.join(root, "pfps")
        if os.path.isdir(path):
            for f in os.listdir(path):
                filepath = os.path.join(path, f)
                with open(filepath, "rb") as f:
                    try:
                        await self.user.edit(avatar=f.read())
                    except discord.HTTPException:
                        pass

    def _get_prefix(self, debug: bool = None):
        if debug is None:
            debug = config.DEBUG

        async def get_prefix(bot: commands.Bot, message: discord.Message = None) -> str:
            if debug:
                return "amyd"
            prefixes = ["amyr"]
            return commands.when_mentioned_or(*prefixes)(bot, message)

        return get_prefix

    async def get_formatted_prefix(self, debug: bool = None):
        command_prefix = self._get_prefix(debug=debug)

        if inspect.isfunction(command_prefix):
            command_prefix = await command_prefix(bot)

        if isinstance(command_prefix, list):
            command_prefix = command_prefix[-1]

        return command_prefix

    @property
    def owner(self) -> discord.User:
        return self.get_user(self.owner_id)

    async def is_owner(self, user: discord.User) -> bool:
        return user.id == self.owner_id or user.id in self.owner_ids

    def sync_is_owner(self, user: discord.User) -> bool:
        return user.id == self.owner_id or user.id in self.owner_ids

    async def on_connect(self) -> None:
        self.logger.info("Connected to discord gateway")

    async def load_extensions(self) -> None:
        rootdir = os.getcwd()
        direc = os.path.join(rootdir, "modules")
        for root, _, files in os.walk(direc):
            prefix = root[len(rootdir) + 1 :].replace("\\", "/").replace("/", ".")

            parent = prefix.split(".")[-1]  # get the parent of the file
            if parent == "__pycache__":  # ignore pycache folders
                continue

            for file in files:  # iterate through all files in a subdirectory
                if not file.endswith(".py"):
                    continue

                fn = file[:-3]

                if os.path.isdir(os.path.join(prefix, fn)):
                    continue

                name = f"{prefix}.{fn}"
                try:
                    imp = importlib.import_module(name)
                except Exception as exc:
                    exc = "".join(
                        traceback.format_exception(type(exc), exc, exc.__traceback__)
                    )

                    self.logger.error(f"Error occured loading module {name}:\n{exc}")
                else:
                    try:
                        source = inspect.getsource(imp)
                    except Exception:
                        pass
                    else:
                        ast_tree = ast.parse(source)
                        imports = [
                            x.module
                            if isinstance(x, ast.ImportFrom)
                            else x.names[0].name
                            for x in ast_tree.body
                            if any(
                                isinstance(x, i) for i in [ast.Import, ast.ImportFrom]
                            )
                        ]
                        clean_imports = [
                            x if not isinstance(x, ModuleType) else x.__name__
                            for x in filter(lambda x: x is not None, imports)
                            if x.startswith("modules")
                        ]

                        self.module_relatives[name] = clean_imports

                        if hasattr(imp, "setup"):
                            try:
                                await self.load_extension(name)
                            except Exception as exc:
                                exc = "".join(
                                    traceback.format_exception(
                                        type(exc), exc, exc.__traceback__
                                    )
                                )

                                self.logger.error(
                                    f"Error occured loading module {name}:\n{exc}"
                                )
                            else:
                                self.logger.info(f"Succesfully loaded module {name}")

    async def setup_hook(self) -> None:
        discord.utils.setup_logging()
        self.pfp_rotation.start()

        self.session = aiohttp.ClientSession()
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch()
        self.bcontext = await self.browser.new_context()

        await self.load_extensions()
        await self.update_command_callbacks()

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        await self.process_commands(message)

    def _generate_ct_name(self, command_name: str):
        for _ in range(100):
            id_part = "".join(random.choices(string.digits, k=5))
            name = command_name.replace(" ", "-") + "-" + id_part

            if name not in self.command_tasks.keys():
                return name

        raise RecursionError(
            "maximum command task name generation error recursion limit reached"
        )

    def _create_callback(self, command: commands.Command):
        command._original_callback = command.callback

        async def callback(cog, *args, **kwargs):
            if isinstance(cog, commands.Context):
                ctx = cog
            else:
                ctx = args[0]
            command: commands.Command = ctx.command
            cb = command._original_callback

            task = asyncio.create_task(cb(cog, *args, **kwargs))
            name = self._generate_ct_name(command.qualified_name)
            obj = {"user": ctx.author.id, "task": task, "created": datetime.utcnow()}
            self.command_tasks[name] = obj
            ctx._task_name = name

            def done_callback(result: asyncio.Future):
                self.command_tasks.pop(name, None)

            task.add_done_callback(done_callback)
            return await task

        return callback

    async def update_command_callbacks(self):
        for command in self.walk_commands():
            command._callback = self._create_callback(command)

    async def on_ready(self) -> None:
        info = {
            "Statistics": {"Users": len(self.users), "Guilds": len(self.guilds)},
            "Modules": {
                "Commands": len(list(self.walk_commands())),
                "Events": len(self._listeners),
            },
        }

        self.logger.info(f"Logged in as {self.user}")

        for name, data in info.items():
            self.logger.info(name)
            texts = [f"{k}: {v}" for k, v in data.items()]
            text = ascii_list(texts)
            for txt in text:
                self.logger.info(indent(txt, "  "))

        with open("restart.json", "r") as f:
            data = json.load(f)
            if not data:
                return

            guild = data.get("guild")
            channel = data.get("channel")
            message = data.get("message")
            time = datetime.utcnow().timestamp() - data.get("time")

            if not (guild or channel or message or time):
                return

            try:
                guild: discord.Guild = self.get_guild(guild)
                channel: discord.TextChannel = guild.get_channel(channel)
                message = await channel.fetch_message(message)
            except AttributeError:
                return

            took = humanfriendly.format_timespan(int(time))
            await message.reply(f"Restart took {took}")
            with open("restart.json", "w") as w:
                w.write("{}")
                w.close()
            f.close()

    async def close(self, updater: Callable = None) -> None:
        tasks = {"bot": super().close, "session": self.session.close}

        async def log(message: str, attr: str = None):
            if updater:
                await updater(message)
            getattr(self.logger, attr or "log")(message)

        for task, func in tasks.items():
            try:
                await func()
            except Exception as exc:
                exc = "\n".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                )

                await log(f"Error occured closing {task} ({func}):\n{exc}", "error")

        await super().close()

    async def get_context(self, message, *, cls=None) -> Context:
        return await super().get_context(message, cls=cls or self.context)

    def setup_discord_logger(self) -> None:
        logger = logging.getLogger("discord")
        logger.setLevel(logging.INFO)
        logging.getLogger("discord.http").setLevel(logging.INFO)

        handler = logging.handlers.RotatingFileHandler(
            filename="logs/discord.log",
            encoding="utf-8",
            maxBytes=32 * 1024 * 1024,  # 32 MiB
            backupCount=5,  # Rotate through 5 files
        )
        dt_fmt = "%Y-%m-%d %H:%M:%S"
        formatter = logging.Formatter(
            "[{asctime}] [{levelname:<8}] {name}: {message}", dt_fmt, style="{"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    def setup_bot_logger(self) -> None:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)

        handler = logging.handlers.RotatingFileHandler(
            filename="logs/bot.log",
            encoding="utf-8",
            maxBytes=32 * 1024 * 1024,  # 32 MiB
            backupCount=5,  # Rotate through 5 files
        )
        dt_fmt = "%Y-%m-%d %H:%M:%S"
        formatter = logging.Formatter(
            "[{asctime}] [{levelname:<8}] {name}: {message}", dt_fmt, style="{"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        self.logger = logger

    def setup_loggers(self) -> None:
        self.setup_discord_logger()
        self.setup_bot_logger()

    def startup(self) -> None:
        self.setup_loggers()

        return self.run(config.TOKEN, log_handler=None)


intents = discord.Intents.all()

bot = amyrin(
    allowed_mentions=discord.AllowedMentions.none(),
    intents=intents,
    strip_after_prefix=True,
    case_insensitive=True,
)


# stole from https://gist.github.com/AbstractUmbra/a9c188797ae194e592efe05fa129c57f
@bot.command()
@commands.guild_only()
@commands.is_owner()
async def sync(
    ctx: Context,
    guilds: Greedy[discord.Object],
    spec: Optional[Literal["~", "*", "^"]] = None,
) -> None:
    if not guilds:
        if spec == "~":
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "*":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "^":
            ctx.bot.tree.clear_commands(guild=ctx.guild)
            await ctx.bot.tree.sync(guild=ctx.guild)
            synced = []
        else:
            synced = await ctx.bot.tree.sync()

        await ctx.send(
            f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
        )
        return

    ret = 0
    for guild in guilds:
        try:
            await ctx.bot.tree.sync(guild=guild)
        except discord.HTTPException:
            pass
        else:
            ret += 1

    await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")
