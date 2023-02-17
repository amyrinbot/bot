import ast
import asyncio
import inspect
import json
import os
import random
import re
import string
import sys
import textwrap
import traceback
from copy import copy
from datetime import datetime
from typing import AsyncGenerator, Dict

import discord
import import_expression
from discord.ext import commands
from jishaku.codeblocks import codeblock_converter
from jishaku.repl import KeywordTransformer

from core.bot import amyrin
from modules.util.updater import Updater
from modules.views.paginator import WrapList, paginate
from modules.views.pull import PullView

from . import *


def parse_code(code: str) -> ast.Module:
    code = f"""async def func():
    from importlib import import_module as {import_expression.constants.IMPORTER}
{textwrap.indent(code, '    ')}"""

    code: ast.Module = import_expression.parse(code)
    ast.fix_missing_locations(code)
    block: ast.AsyncFunctionDef = code.body[-1]
    KeywordTransformer().generic_visit(block)

    last = block.body[-1]

    if not isinstance(last, ast.Expr):
        return code

    if not isinstance(last.value, ast.Yield):
        assign = ast.Yield(last.value)
        ast.copy_location(assign, last)
        _yield = ast.Expr(assign)
        ast.copy_location(_yield, last)
        block.body[-1] = _yield

    return code


async def evaluate_code(ctx: commands.Context, env: dict, code: str):
    try:
        res = parse_code(code)
        code = compile(res, filename="<eval>", mode="exec")
    except Exception as exc:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        result = f"```py\n{tb}```"
        return await ctx.send(result)

    """ Evaluating """
    result = None
    async with Updater(ctx):
        try:
            exec(code, env)
            func = env.get("func")
            if inspect.isasyncgenfunction(func):
                return func
            else:
                await func()
        except Exception as exc:
            result = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )

        if result is not None and len(str(result.strip())) > 0:
            return result


async def handle_async_generator(
    ctx: commands.Context, func: AsyncGenerator, *args, **kwargs
):
    async for i in func():
        if i is not None:
            await send(ctx, i, *args, **kwargs)


async def send(ctx: commands.Context, result, *args, **kwargs):
    if isinstance(result, list):
        if all(isinstance(i, discord.Embed) for i in result):
            return await ctx.send(embeds=result, *args, **kwargs)
        if all(isinstance(i, discord.Attachment) for i in result):
            return await ctx.send(
                files=[await i.to_file() for i in result], *args, **kwargs
            )
        if all(isinstance(i, discord.File) for i in result):
            return await ctx.send(files=result, *args, **kwargs)
        return await ctx.send(str(result), *args, **kwargs)
    if isinstance(result, discord.Embed):
        return await ctx.send(embed=result, *args, **kwargs)
    if isinstance(result, discord.Attachment):
        return await ctx.send(file=await result.to_file(), *args, **kwargs)
    if isinstance(result, discord.File):
        return await ctx.send(file=result, *args, **kwargs)
    if isinstance(result, str):
        if len(result.splitlines()) > 1:
            return await ctx.send(
                f"```py\n{str(result).replace('``', '`​`')}```", *args, **kwargs
            )
        return await ctx.send(result, *args, **kwargs)
    if isinstance(result, discord.ui.View):
        return await ctx.send(view=result, *args, **kwargs)
    if result is None:
        return

    return await ctx.send(str(result), *args, **kwargs)


class Developer(commands.Cog, command_attrs={"hidden": True}):
    def __init__(self, bot):
        super().__init__()
        self.bot: amyrin = bot
        self.module_regex = re.compile(r"(?P<module>modules\/.+)\.py")

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    async def shell(self, code: str, wait: bool = True):
        proc = await asyncio.subprocess.create_subprocess_shell(
            code, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        if wait:
            await proc.wait()
        return tuple(i.decode() for i in await proc.communicate())

    @command(
        commands.group,
        name="eval",
        aliases=["e"],
        examples=['{prefix}eval print("hot gay sex")'],
        permissions=CommandPermissions(template=PermissionTemplates.text_command),
        invoke_without_command=True,
    )
    async def _eval(self, ctx, *, code: codeblock_converter):
        code = code.content

        # omg console.log in python 😱😰😰
        class console:
            @classmethod
            def log(cls, *args, **kwargs):
                print(*args, **kwargs)

        ref = None if ctx.message.reference is None else ctx.message.reference.resolved
        env = {
            "discord": discord,
            "commands": commands,
            "author": ctx.message.author,
            "bot": self.bot,
            "channel": ctx.message.channel,
            "find": discord.utils.find,
            "ctx": ctx,
            "get": discord.utils.get,
            "guild": ctx.message.guild,
            "message": ctx.message,
            "msg": ctx.message,
            "src": inspect.getsource,
            "srcls": inspect.getsourcelines,
            "commands": commands,
            "console": console,
            "ref": ref,
            "rf": ref,
        }

        """ Code Parsing """

        result = await evaluate_code(ctx, env, code)

        if inspect.isasyncgenfunction(result):
            return await handle_async_generator(ctx, result, edit=False)

        if result is not None:
            await send(ctx, result, edit=False)

    @command(
        commands.command,
        name="as",
        aliases=["su"],
        examples=["{prefix}as flowerpad#0001 help"],
        permissions=CommandPermissions(template=PermissionTemplates.text_command),
    )
    async def _as(self, ctx, user: discord.Member, *, command: str):
        prefix = await self.bot.get_formatted_prefix()
        msg = copy(ctx.message)
        msg.content = f"{prefix}{command}"
        msg.author = user
        await self.bot.process_commands(msg)

    @command(
        commands.command,
        aliases=["pull"],
        examples=["{prefix}update"],
        permissions=CommandPermissions(template=PermissionTemplates.text_command),
    )
    async def update(self, ctx: commands.Context):
        async with ctx.typing():
            result = await self.shell("git pull --force --stat")

        output = "\n".join(i.strip() for i in result)

        if output.lower() == "already up to date.":
            return await ctx.send("Already up to date")

        modules = [x.replace(os.sep, ".") for x in self.module_regex.findall(output)]
        reloaded = "\n".join(modules)
        description = f"```sh\n{output}```"
        if reloaded:
            description += f"\n\nChanged Modules:\n{reloaded}"

        embed = discord.Embed(description=description, color=self.bot.color)
        await ctx.send(embed=embed, view=PullView(ctx, modules=modules))

    @command(
        commands.command,
        aliases=["rs"],
        examples=["{prefix}restart"],
        permissions=CommandPermissions(template=PermissionTemplates.text_command),
    )
    async def restart(self, ctx: commands.Context):
        await ctx.message.reply("Now restarting bot")

        with open("restart.json", "w") as f:
            data = {
                "guild": ctx.guild.id,
                "channel": ctx.channel.id,
                "message": ctx.message.id,
                "time": datetime.utcnow().timestamp(),
            }
            f.write(json.dumps(data, indent=4))
            f.close()

        ctx._message: discord.Message = None

        async def updater(message: str):
            if self._message:
                content = ctx._message.content
                content += "\n" + message
                ctx._message = await ctx._message.edit(content=content)
            else:
                ctx._message = await ctx.send(message)

        await self.bot.close(updater)


async def setup(bot):
    await bot.add_cog(Developer(bot))
