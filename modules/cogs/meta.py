import inspect
import os
import pathlib
from datetime import datetime

import discord
import humanfriendly
import humanize
import psutil
from discord.ext import commands

from core.bot import amyrin

from . import *


class Meta(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot: amyrin = bot

    def _format_uptime(self):
        delta_uptime = datetime.utcnow() - self.bot.uptime
        return humanfriendly.format_timespan(int(delta_uptime.total_seconds()))

    @command(
        description="Get my full source code or the source code of a specific command",
        aliases=["src"],
        examples=["{prefix}source calculator"],
    )
    async def source(
        self, ctx: commands.Context | discord.Interaction, *, command: str = None
    ):
        URL = "https://github.com/amyrinbot/bot"
        BRANCH = "main"

        if command is None:
            return await ctx.send(URL)

        if command == "help":
            src = type(self.bot.help_command)
            filename = inspect.getsourcefile(src)
        else:
            cmd = self.bot.get_command(command)
            if cmd is None:
                return await ctx.send("Command was not found.")

            src = cmd.callback.__code__
            filename = src.co_filename

        if filename is None:
            return await ctx.send(f"Source for command `{command}` could not be found.")

        lines, start = inspect.getsourcelines(src)
        end = start + len(lines) - 1
        location = os.path.relpath(filename).replace("\\", "/")

        source_url = f"<{URL}/blob/{BRANCH}/{location}/#L{start}-L{end}>"
        await ctx.send(source_url)

    @command(description="Get my ping", aliases=["latency"], examples=["{prefix}ping"])
    async def ping(self, ctx: commands.Context | discord.Interaction):
        websocket = round(self.bot.latency * 1000, 2)

        em = discord.Embed(title="Latency", color=self.bot.color)
        em.add_field(
            name=f"Websocket",
            value=f"```diff\n{websocket}ms```",
        )

        await ctx.send(embed=em)

    @command(description="Get my uptime", examples=["{prefix}uptime"])
    async def uptime(self, ctx: commands.Context | discord.Interaction):
        uptime = self._format_uptime()

        await ctx.send(f"I have been up for {uptime}")

    @command(
        description="Get info about oynx's file stats and host stats",
        examples=["{prefix}about"],
    )
    @commands.cooldown(1, 20)
    async def about(self, ctx: commands.Context | discord.Interaction):
        path = pathlib.Path(os.getcwd())
        ignored = [
            pathlib.Path(os.path.join(path, "rtfs_repos")),
        ]

        def line_count():
            files = classes = funcs = comments = lines = characters = 0
            for f in path.rglob(f"*.py"):
                if any(parent in ignored for parent in f.parents):
                    continue
                files += 1
                with open(f) as of:
                    characters += len(open(f).read())
                    for line in of.readlines():
                        line = line.strip()
                        if line.startswith("class"):
                            classes += 1
                        if line.startswith("def"):
                            funcs += 1
                        if line.startswith("async def"):
                            funcs += 1
                        if "#" in line:
                            comments += 1
                        lines += 1
            return files, classes, funcs, comments, lines, characters

        async with ctx.typing():
            (
                files,
                classes,
                funcs,
                comments,
                lines,
                characters,
            ) = await self.bot.loop.run_in_executor(None, line_count)

        pid = os.getpid()
        process = psutil.Process(pid)

        uptime = self._format_uptime()

        em = discord.Embed(description=self.bot.description, color=self.bot.color)
        em.set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar.url)
        em.add_field(name="Developer", value=str(self.bot.owner))
        em.add_field(name="Uptime", value=uptime)
        em.add_field(name="​", value="​")

        f_stats = {
            "Characters": characters,
            "Functions": funcs,
            "Comments": comments,
            "Classes": classes,
            "Files": files,
            "Lines": lines,
        }

        f_stats_str = "\n".join(f"{k}: {v}" for k, v in f_stats.items())

        em.add_field(
            name="File Statistics",
            value=f"""
```py
{f_stats_str}
```
            """,
            inline=True,
        )
        em.add_field(
            name="Host Statistics",
            value=f"""
```py
Process: {process.name()} ({process.pid})
Process started: {humanize.naturaltime(datetime.fromtimestamp(int(process.create_time())))}
CPU Usage: {psutil.cpu_percent()}%
Memory Usage: {psutil.virtual_memory().percent}%
Disk Used: {psutil.disk_usage(str(path)).percent}%
```
""",
        )

        await ctx.send(embed=em)


async def setup(bot):
    await bot.add_cog(Meta(bot))
