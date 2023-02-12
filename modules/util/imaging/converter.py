import re
import emoji
from io import BytesIO

from aiohttp import ClientSession
from bs4 import BeautifulSoup
from discord.ext import commands

from modules.util.converters import SpecificUserConverter
from modules.util.executor import executor
from urllib.parse import urlparse

TENOR_REGEX = r"https?:\/\/tenor\.com\/view\/.+"
URL_REGEX = (
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)

CONTENT_TYPES = ["image/gif", "image/jpeg", "image/png", "image/webp"]


async def scrape_tenor(session: ClientSession, url: str):
    @executor()
    def parse(content: str):
        soup = BeautifulSoup(content, "lxml")
        gif = soup.find("div", class_="Gif")
        if gif:
            img = gif.find("img")
            if img:
                return img.get("src")

    async with session.get(url) as resp:
        if resp.status != 200:
            return

        content = await resp.text()
        return await parse(content)


async def read_url(url: str, session: ClientSession, *args, **kwargs):
    resp = await session.get(url, *args, **kwargs)
    content_type = resp.headers.get("Content-Type")
    data = await resp.read()
    if len(data) > 16 * 1024 * 1024:  # 16 mb
        return
    if content_type in CONTENT_TYPES:
        return BytesIO(data)


async def parse_url(url: str, session: ClientSession):
    if re.match(TENOR_REGEX, url) and (tenor := await scrape_tenor(session, url)):
        url = tenor

    return await read_url(url, session)


class ImageConverter(commands.Converter):
    async def convert(
        self,
        ctx: commands.Context,
        argument: str,
        *,
        relative: bool = True,
        animated: bool = True,
        fallback: bool = True,
        allow_emojis: bool = True,
    ) -> str:
        argument = argument.strip()
        message = ctx.message

        used = False

        if message.attachments:
            if result := await read_url(message.attachments[0].url, ctx.bot.session):
                return result, used

        if message.reference and relative:
            if message.reference.resolved:
                ref = message.reference.resolved
                if ref.attachments:
                    if result := await read_url(
                        ref.attachments[0].url, ctx.bot.session
                    ):
                        return result, used
                argument = ref.content

        try:
            user = await SpecificUserConverter().convert(ctx, argument)
        except Exception:
            pass
        else:
            if not animated:
                return BytesIO(await user.avatar.with_format("png").read()), True
            return BytesIO(await user.avatar.read()), True

        if re.match(URL_REGEX, argument):
            parsed_url = urlparse(argument)
            if str(parsed_url.netloc) not in ("127.0.0.1", "localhost", "0.0.0.0"):
                if result := await parse_url(argument, ctx.bot.session):
                    return result, True

        try:
            emoji_ = await commands.PartialEmojiConverter().convert(ctx, argument)
        except Exception:
            pass
        else:
            return BytesIO(await emoji_.read()), True

        if allow_emojis and emoji.is_emoji(argument):
            url = "https://emojicdn.elk.sh/" + argument
            if result := await read_url(
                url, ctx.bot.session, params={"style": "twitter"}
            ):
                return result, True

        if fallback:
            if not animated:
                return BytesIO(await ctx.author.avatar.with_format("png").read()), False
            return BytesIO(await ctx.author.avatar.read()), False
        return None, False


async def setup(bot):
    pass
