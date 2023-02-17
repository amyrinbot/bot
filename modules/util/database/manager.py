import asyncio
import functools
import os
import random
import string
import traceback
from datetime import datetime
from typing import Callable, List, Self, Union

import asyncpg
import discord
from asyncpg import Pool, Record
from discord.ext import commands, tasks

from modules.util.database.exceptions import (AlreadyFollowingError,
                                              ErrorAlreadyFixed, ErrorNotFound,
                                              MaximumErrorFollowersReached,
                                              NotFollowingError)

root_dir = os.path.dirname(os.path.realpath(__file__))


class DatabaseManager:
    def __init__(self, bot: commands.Bot, default_prefix: str) -> None:
        self.bot = bot
        self.default_prefix = default_prefix

        self._pool: Pool = None
        self._caching_task: asyncio.Task
        self._cache: dict = {"guilds": {}, "blacklist": {}, "errors": {}}

    async def wait_until_cached(self) -> None:
        while not self._cached:
            await asyncio.sleep(0.1)

    @tasks.loop(minutes=10)
    async def remove_guilds(self) -> None:
        await self.bot.wait_until_ready()
        guilds = await self._pool.fetch("SELECT guild_id FROM guilds")
        query = []
        for guild in guilds:
            guild = guild.get("guild_id")
            if not discord.utils.get(self.bot.guilds, id=guild):
                query_str = f"DELETE FROM guilds WHERE guild_id = {guild};"
                query.append(query_str)
                if item := discord.utils.find(
                    lambda x: x.get("guild_id") == guild, self._cache["guilds"]
                ):
                    self._cache["guilds"].remove(item)

        if query:
            query_str = "\n".join(query)
            print(query_str)
            await self._pool.execute(query_str)

    async def add_new_guilds(self) -> None:
        await self.bot.wait_until_ready()

        query = map(
            lambda x: x["guild_id"],
            await self._pool.fetch("SELECT guild_id FROM guilds"),
        )

        for guild in self.bot.guilds:
            if guild.id not in query:
                await self.add_guild(guild)

    async def _auto_cache(self) -> None:
        for table in self._cache.keys():
            content: List[Record] = await self._pool.fetch(f"SELECT * FROM {table}")

            for entry in content:
                data = dict(entry.items())
                self._cache[table] = data

        self._cached = True

    @classmethod
    async def start(
        cls: Self,
        bot: commands.Bot,
        default_prefix: str,
        database: str,
        host: str,
        port: str,
        user: str,
        password: str,
        *args,
        **kwargs,
    ) -> Self:
        schema_path = os.path.join(root_dir, "schema.sql")

        if not os.path.exists(schema_path):
            raise Exception("schema.sql file doesn't exist")

        self: Self = cls(bot=bot, default_prefix=default_prefix, *args, **kwargs)
        self._pool = await asyncpg.create_pool(
            database=database, host=host, port=port, user=user, password=password
        )

        with open(schema_path) as schema:
            content = schema.read()
            await self._pool.execute(content)

        self._caching_task = asyncio.create_task(self._auto_cache())
        await self._caching_task
        asyncio.create_task(self.add_new_guilds())
        self.remove_guilds.start()

        return self

    async def close(self):
        return await self._pool.close()

    async def get_disabled_commands(self, guild: discord.Guild):
        if guild is None:
            return []

        if guild.id in self._cache["guilds"]:
            return self._cache["guilds"][guild.id].get("disabled_commands")

        result = await self._pool.fetchrow(
            "SELECT * FROM guilds WHERE guild_id = $1", guild.id
        )

        if not result:
            await self.add_guild(guild)

        self._cache["guilds"][guild.id] = {
            "guild_id": guild.id,
            "disabled_commands": result["disabled_commands"],
        }
        return result["disabled_commands"]

    async def add_disabled_command(self, guild: discord.Guild, command: str):
        cmd: commands.Command = self.bot.tree.get_command(command)
        if cmd is None:
            raise commands.CommandNotFound()

        await self._pool.execute(
            "UPDATE guilds SET disabled_commands = array_append(disabled_commands, $2) WHERE guild_id = $1",
            guild.id,
            cmd.qualified_name,
        )

        if guild.id in self._cache["guilds"]:
            self._cache["guilds"][guild.id]["disabled_commands"].append(
                cmd.qualified_name
            )
        else:
            result = await self._pool.fetchrow(
                "SELECT * FROM guilds WHERE guild_id = $1", guild.id
            )
            self._cache["guilds"][guild.id] = {
                "guild_id": guild.id,
                "disabled_commands": result["disabled_commands"],
            }

    async def remove_disabled_command(self, guild: discord.Guild, command: str):
        cmd: commands.Command = self.bot.tree.get_command(command)
        if cmd is None:
            raise commands.CommandNotFound()

        await self._pool.execute(
            "UPDATE guilds SET disabled_commands = array_remove(disabled_commands, $2) WHERE guild_id = $1",
            guild.id,
            cmd.qualified_name,
        )

        if guild.id in self._cache["guilds"]:
            self._cache["guilds"][guild.id]["disabled_commands"].remove(
                cmd.qualified_name
            )
        else:
            result = await self._pool.fetchrow(
                "SELECT * FROM guilds WHERE guild_id = $1", guild.id
            )
            self._cache["guilds"][guild.id] = {
                "guild_id": guild.id,
                "disabled_commands": result["disabled_commands"],
            }

    async def add_error(
        self, interaction: discord.Interaction | commands.Context, exception: Exception
    ):
        if hasattr(interaction, "interaction"):
            interaction = interaction.interaction

        if isinstance(interaction, discord.Interaction):
            author = interaction.user.id
        else:
            author = interaction.author.id
        guild_id = 0 if not interaction.guild else interaction.guild.id

        if isinstance(interaction, discord.Interaction):
            parameters = interaction.namespace
        else:
            parameters = dict(
                {k: v for k, v in interaction.kwargs.items() if v is not None}
            ).items()
        formatted_parameters = " ".join(
            f"({name}={param})" for name, param in parameters
        )
        created = datetime.utcnow()
        exc = "".join(
            traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
        )

        combinations = string.ascii_letters + string.digits
        password = "".join(random.choices(combinations, k=32))
        error_url = str(
            await self.bot.myst.create_paste(
                filename="error.py", content=exc, password=password
            )
        )
        error = f"{exception.__class__.__name__}: {exception}"

        result = await self._pool.fetch("SELECT * FROM errors")
        index = len(result)
        item = [i for i in result if i["error"] == error and not i["fixed"]]
        if not item:
            index += 1
            query = (
                "INSERT INTO errors (code, author, guild_id, error, error_url, password, parameters, created, fixed, followers) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)"
            )

            await self._pool.execute(
                query,
                index,
                author,
                guild_id,
                error,
                error_url,
                password,
                formatted_parameters,
                created,
                False,
                [],
            )
            summary = (
                f"Looks like there's been an error running the command, I have created an error with code "
                f"**{index}** which will be reviewed by my developers soon. "
                " If you want to get notified when the issue has been fixed, you can run "
                f"`/error follow {index}`, or if you want to check the status of the error, "
                f"you can run `/error status {index}`."
            )
        else:
            index = item[0]["code"]
            summary = (
                f"Looks like there's been an error running the command, the error is already in the database "
                f"with code **{index}** and will be reviewed by my developers soon. "
                f" If you want to get notified when the issue has been fixed, you can run "
                f"`/error follow {index}`, or if you want to check the status of the error, "
                f"you can run `/error status {index}`."
            )
        return summary

    async def get_error(self, code: int):
        query = await self._pool.fetchrow("SELECT * FROM errors WHERE code = $1", code)
        if not query:
            raise ErrorNotFound("That error does not exist")
        return query

    async def get_errors(self):
        errors = await self._pool.fetch("SELECT * FROM errors ORDER BY code")
        return [i for i in errors if not i["fixed"]]

    async def fix_error(self, code: int, note: str = None):
        query = await self._pool.fetchrow(
            "SELECT followers FROM errors WHERE code = $1", code
        )
        if not query:
            raise ErrorNotFound("That error does not exist")

        followers = query["followers"]

        for follower in followers:
            user = self.bot.get_user(follower)
            if user:
                try:
                    await user.send(
                        f"Error `{code}` has been fixed{f' with note `{note}`' if note else ''}, "
                        "tho you can still get notifications if this fix is not working or an accident, "
                        f"if you don't want this, run /error unfollow {code}."
                    )
                except discord.Forbidden:
                    pass

        await self._pool.execute(
            "UPDATE errors SET fixed = $2 WHERE code = $1", code, True
        )

    async def unfix_error(self, code: int, note: str):
        query = await self._pool.fetchrow(
            "SELECT followers FROM errors WHERE code = $1", code
        )
        if not query:
            raise ErrorNotFound("That error does not exist")

        followers = query["followers"]

        for follower in followers:
            user = self.bot.get_user(follower)
            if user:
                try:
                    await user.send(
                        f"Error `{code}`'s fixed status has been removed because {note}"
                    )
                except discord.Forbidden:
                    pass

        await self._pool.execute(
            "UPDATE errors SET fixed = $2 WHERE code = $1", code, False
        )

    async def follow_error(self, code: int, user: discord.Member | discord.User | int):
        if isinstance(user, (discord.Member, discord.User)):
            user = user.id

        query = await self._pool.fetchrow("SELECT * FROM errors WHERE code = $1", code)
        if query is None:
            raise ErrorNotFound("Error does not exist")
        if query["fixed"]:
            raise ErrorAlreadyFixed("That error is already fixed")

        followers = query["followers"]
        if user in followers:
            raise AlreadyFollowingError("You are already following this error")
        if len(followers) >= 5:
            raise MaximumErrorFollowersReached(
                "This error already has 5 followers, thus you cannot follow it"
            )
        followers.append(user)

        await self._pool.execute(
            "UPDATE errors SET followers = $2 WHERE code = $1", code, followers
        )

    async def unfollow_error(
        self, code: int, user: discord.Member | discord.User | int
    ):
        if isinstance(user, (discord.Member, discord.User)):
            user = user.id

        query = await self._pool.fetchrow("SELECT * FROM errors WHERE code = $1", code)
        if query is None:
            raise ErrorNotFound("Error does not exist")
        if query["fixed"]:
            raise ErrorAlreadyFixed("That error is already fixed")

        followers = query["followers"]
        if user not in followers:
            raise NotFollowingError("You aren't following that error")
        followers.remove(user)

        await self._pool.execute(
            "UPDATE errors SET followers = $2 WHERE code = $1", code, followers
        )

    async def add_blacklist(
        self, user: discord.Member | discord.User | int, reason: str
    ):
        if isinstance(user, (discord.User, discord.Member)):
            user = user.id

        await self._pool.execute(
            "INSERT INTO blacklist (user_id, reason) VALUES ($1, $2)", user, reason
        )
        self._cache["blacklist"][user] = {"user_id": user, "reason": reason}

    async def remove_blacklist(self, user: discord.Member | discord.User | int):
        if isinstance(user, (discord.User, discord.Member)):
            user = user.id

        await self._pool.execute("DELETE FROM blacklist WHERE user_id = $1", user)
        if user in self._cache["blacklist"]:
            del self._cache["blacklist"][user]

    async def is_blacklisted(self, user: discord.Member | discord.User | int):
        if isinstance(user, (discord.Member, discord.User)):
            user = user.id

        if user in self._cache["blacklist"]:
            return self._cache["blacklist"][user]

    async def remove_guild(self, guild: discord.Guild | int):
        if isinstance(guild, discord.Guild):
            guild = guild.id

        await self._pool.execute("DELETE FROM guilds WHERE guild_id = $1", guild)

        if guild in self._cache["guilds"]:
            del self._cache["guilds"][guild]

    async def add_guild(self, guild: discord.Guild | int):
        if isinstance(guild, discord.Guild):
            guild = guild.id

        query = await self._pool.fetch("SELECT guild_id FROM guilds")

        if guild in [x["guild_id"] for x in query]:
            raise Exception("Guild is already in database")

        if isinstance(self.default_prefix, list):
            default_prefixes = self.default_prefix
        else:
            default_prefixes = [self.default_prefix]
        await self._pool.execute(
            "INSERT INTO guilds (guild_id, prefixes, disabled_commands) VALUES ($1, $2, $3)",
            guild,
            default_prefixes,
            [],
        )

        self._cache["guilds"][guild] = {
            "guild_id": guild,
            "disabled_commands": [],
        }
