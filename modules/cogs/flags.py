from discord.ext import commands


class DownloadFlags(commands.FlagConverter, case_insensitive=True, prefix="--", delimiter=" "):
    format: str = commands.flag(
        name="format", aliases=["fmt"], default="mp4",
        description="The format you want the download to be in."
    )
    compress: bool = commands.flag(
        name="compress", default=False,
        description="Whether you want the final file to be compressed to the guild's max filesize limit."
    )
