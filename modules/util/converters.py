import inspect
import os
import re
from io import BufferedIOBase, BytesIO
from typing import Any
from urllib.parse import urlparse

import aiohttp
import discord
from discord.ext import commands

MENTION_REGEX = re.compile(r"<@(!?)([0-9]*)>")


def format_list(items: list, seperator: str = "or", brackets: str = ""):
    new_items = []
    for i in items:
        if not re.match(MENTION_REGEX, i):
            new_items.append(f"{brackets}{i}{brackets}")
        else:
            new_items.append(str(i))

    msg = ", ".join(list(new_items)[:-1]) + f" {seperator} " + list(new_items)[-1]
    return msg


URL_REGEX = re.compile(
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)


class URLObject:
    def __init__(self, url: str):
        if not URL_REGEX.match(url):
            raise TypeError(f"Invalid url provided")
        self.url = url
        self.filename = url.split("/")[-1]

    async def read(self, *, session=None) -> bytes:
        """Reads this asset."""
        _session = session or aiohttp.ClientSession()
        try:
            async with _session.get(self.url) as resp:
                if resp.status == 200:
                    return await resp.read()
                elif resp.status == 404:
                    raise discord.NotFound(resp, "asset not found")
                elif resp.status == 403:
                    raise discord.Forbidden(resp, "cannot retrieve asset")
                else:
                    raise discord.HTTPException(resp, "failed to get asset")
        finally:
            if not session:
                await _session.close()

    async def save(
        self,
        fp: BufferedIOBase | os.PathLike[Any],
        *,
        data: bytes = None,
        seek_begin: bool = True,
    ) -> int:
        """Saves to an object or buffer."""
        data = data or await self.read()
        if isinstance(fp, BufferedIOBase):
            written = fp.write(data)
            if seek_begin:
                fp.seek(0)
            return written

        with open(fp, "wb") as f:
            return f.write(data)

    @property
    def spoiler(self):
        """Wether the file is a spoiler"""
        return self.name.startswith("SPOILER_")

    @spoiler.setter
    def spoiler(self, value: bool):
        if value != self.spoiler:
            if value is True:
                self.name = f"SPOILER_{self.name}"
            else:
                self.name = self.name.split("_", maxsplit=1)[1]

    async def to_file(self, *, session: aiohttp.ClientSession = None):
        return discord.File(
            BytesIO(await self.read(session=session)), self.name, spoiler=False
        )


class URLConverter(commands.Converter):
    async def convert(
        self, ctx: commands.Context | discord.Interaction, argument: str
    ) -> str:
        parsed_url = urlparse(argument)

        if parsed_url.netloc in (
            "127.0.0.1",
            "localhost",
            "0.0.0.0",
        ) and not await ctx.bot.is_owner(ctx.author):
            raise commands.BadArgument("Invalid URL")

        return argument


class SpecificUserConverter(commands.Converter):
    """User Converter class that only supports IDs and mentions"""

    async def _get_user(self, bot: commands.Bot, argument: int):
        user = bot.get_user(argument)
        if user:
            return user
        return await bot.fetch_user(argument)

    async def convert(self, ctx: commands.Context, argument: str):
        is_digits = all(char.isdigit() for char in argument)

        if is_digits:
            if user := await self._get_user(ctx.bot, int(argument)):
                return user

        if match := re.match(r"<@!?([0-9]+)>", argument):
            if user := await self._get_user(ctx.bot, int(match.group(1))):
                return user

        raise commands.BadArgument("Failed to convert argument to user")


class FileConverter(commands.Converter):
    async def convert(
        self, ctx: commands.Context | discord.Interaction, file: str = None
    ) -> discord.Attachment | URLObject:
        if file is None:
            if ctx.message.attachments:
                attachment = ctx.message.attachments[0]
            elif ctx.message.reference:
                if ctx.message.reference.resolved.attachments:
                    attachment = ctx.message.reference.resolved.attachments[0]
                else:
                    raise commands.MissingRequiredArgument(
                        inspect.Parameter("file", inspect.Parameter.KEYWORD_ONLY)
                    )
            else:
                raise commands.MissingRequiredArgument(
                    inspect.Parameter("file", inspect.Parameter.KEYWORD_ONLY)
                )
        else:
            attachment = URLObject(file)

        return attachment
