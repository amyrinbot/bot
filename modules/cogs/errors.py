import random
import re
import string
from typing import List

import discord
from discord.ext import commands

import core
from core.bot import amyrin
from core.constants import *
from modules.views.paginator import paginate

from . import *


class Errors(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot: amyrin = bot

    async def add_to_files(
        self,
        ctx: commands.Context,
        content: str,
        files: List[discord.File],
        *args,
        **kwargs,
    ):
        file = await ctx.string_to_file(content, *args, **kwargs)
        files.append(file)
        return file.filename

    @command(
        commands.hybrid_group,
        description="Get information on an error",
        examples=["{prefix}error 51"],
        invoke_without_command=True,
    )
    @commands.is_owner()
    async def error(self, ctx: commands.Context, code: int):
        query = await self.bot.db.get_error(code)

        if isinstance(query, core.DatabaseException):
            return await ctx.send(query.message)

        author = str(self.bot.get_user(query["author"]))
        guild = (
            None
            if not self.bot.get_guild(query["guild_id"])
            else self.bot.get_guild(query["guild_id"]).name
        )

        error = query["error"]
        error_url = query["error_url"]
        password = query["password"]
        parameters = query["parameters"]

        created = discord.utils.format_dt(query["created"], "F")
        followers = ", ".join(str(self.bot.get_user(i)) for i in query["followers"])
        fixed = CHECKMARK if query["fixed"] else CROSSMARK

        em = discord.Embed(
            title=f"Error {code}",
            description=f"""
**Error**: ```py\n{error}\n```
**Full Error**: {error_url}
**Password**: ||{password}||

**Author**: {author}
**Guild**: {guild}
**Parameters**: {parameters}
**Time**: {created}
**Followers**: {'N/A' if followers == '' else followers}
**Fixed**: {fixed}
""",
            color=self.bot.color,
        )
        await ctx.send(embed=em)

    @command(
        error.command,
        name="fix",
        description="Mark an error as fixed.",
        examples=["{prefix}error fix 51"],
        hidden=True,
    )
    @commands.is_owner()
    async def error_fix(self, ctx, code: int, *, note: str = None):
        query = await self.bot.db.fix_error(code, note=note)

        if isinstance(query, core.DatabaseException):
            return await ctx.send(query.message)

        await ctx.message.add_reaction(CHECKMARK)

    @command(
        error.command,
        name="massfix",
        description="Mark errors as fixed.",
        examples=["{prefix}error massunfix 51 55 6"],
        aliases=["mf"],
        hidden=True,
    )
    @commands.is_owner()
    async def error_massfix(self, ctx, *, codes: str):
        split_codes = codes.split()
        codes = []

        for code in split_codes:
            match = re.match(r"(?P<start>\d+)-(?P<end>\d+)", code)

            start = int(match.group("start"))
            end = int(match.group("end"))

            if match:
                for v in range(start, end + 1):
                    codes.append(v)
            else:
                try:
                    code = int(code)
                except ValueError:
                    continue
                else:
                    codes.append(code)

        errors = {}
        for code in codes:
            query = await self.bot.db.fix_error(code)

            if isinstance(query, core.DatabaseException):
                errors[code] = query.message

        em = discord.Embed(
            description="\n".join(
                f"{CHECKMARK} {i}"
                if i not in errors
                else f"{CROSSMARK} {i}\n```py\n{errors[i]}```"
                for i in codes
            ),
            color=self.bot.color,
        )
        await ctx.send(embed=em)

    @command(
        error.command,
        name="unfix",
        description="Revert marking an error as fixed.",
        examples=["{prefix}error unfix 51"],
        hidden=True,
    )
    @commands.is_owner()
    async def error_unfix(self, ctx, code: int, *, note: str):
        query = await self.bot.db.unfix_error(code, note=note)

        if isinstance(query, core.DatabaseException):
            return await ctx.send(query.message)

        await ctx.message.add_reaction(CHECKMARK)

    @command(
        error.command,
        name="massunfix",
        examples=["{prefix}error massunfix 51 55 6"],
        description="Revert marking an error as fixed.\nCodes are seperated by `,`",
        aliases=["muf"],
        hidden=True,
    )
    @commands.is_owner()
    async def error_massunfix(self, ctx, codes: str):
        codes = [int(code.strip()) for code in codes.split(",")]

        errors = {}
        for code in codes:
            query = await self.bot.db.unfix_error(code)

            if isinstance(query, core.DatabaseException):
                errors[code] = query.message

        em = discord.Embed(
            description="\n".join(
                f"{CHECKMARK} {i}"
                if i not in errors
                else f"{CROSSMARK} {i}\n```py\n{errors[i]}```"
                for i in codes
            ),
            color=self.bot.color,
        )
        await ctx.send(embed=em)

    @command(
        error.command,
        name="status",
        examples=["{prefix}error status 51"],
        description="Check the status of an error",
    )
    async def error_status(self, ctx: commands.Context, code: int):
        error = await self.bot.db.get_error(code)

        await ctx.send(f"Error {code} is {'not ' if not error['fixed'] else ''}fixed")

    @command(
        error.command,
        examples=["{prefix}error follow 51"],
        name="follow",
        description="Track an error to get notified if it gets fixed",
    )
    async def error_follow(self, ctx: commands.Context, code: int):
        await self.bot.db.follow_error(code, ctx.author)
        await ctx.send(f"You are now following error {code}", ephemeral=True)

    @command(
        error.command,
        name="unfollow",
        examples=["{prefix}error unfollow 51"],
        description="Stop tracking an error, so you wont get any notifications anymore",
    )
    async def error_unfollow(self, ctx: commands.Context, code: int):
        await self.bot.db.unfollow_error(code, ctx.author)
        await ctx.send(f"You are no longer following error {code}", ephemeral=True)

    @command(examples=["{prefix}errors"], description="List all errors")
    async def errors(self, ctx: commands.Context):
        errors = await self.bot.db.get_errors()
        if not errors:
            return await ctx.send(f"{CROSSMARK} There are no unfixed errors")

        embeds = []
        for error in errors:
            em = discord.Embed(color=self.bot.color)

            code = error["code"]
            author = str(self.bot.get_user(error["author"]))
            guild = (
                None
                if not self.bot.get_guild(error["guild_id"])
                else self.bot.get_guild(error["guild_id"]).name
            )

            exception = error["error"]
            error_url = error["error_url"]
            password = error["password"]
            parameters = error["parameters"]

            created = discord.utils.format_dt(error["created"], "F")
            followers = ", ".join(str(self.bot.get_user(i)) for i in error["followers"])
            fixed = CHECKMARK if error["fixed"] else CROSSMARK

            em = discord.Embed(
                title=f"Error {code}",
                description=f"""
**Error**: ```py\n{exception}\n```
**Full Error**: {error_url}
**Password**: ||{discord.utils.escape_markdown(password)}||

**Author**: {author}
**Guild**: {guild}
**Parameters**: {parameters}
**Time**: {created}
**Followers**: {'N/A' if followers == '' else followers}
**Fixed**: {fixed}
""",
                color=self.bot.color,
            )
            embeds.append(em)

        await paginate(
            ctx,
            embeds,
            timeout=30,
            index=errors[0]["code"],
            page_count=errors[-1]["code"],
        )


async def setup(bot):
    await bot.add_cog(Errors(bot))
