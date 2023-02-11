import json
import os
import random
import tempfile
import textwrap
from urllib.parse import urlparse
import discord
import humanfriendly

from discord.ext import commands

from core.bot import amyrin
from modules.util.converters import FileConverter, URLObject, format_list, URLConverter
from modules.util.media.exceptions import AgeLimited, FailedCompressionException, InvalidFormat, LiveStream, MediaException, MissingNginxHandler, TooLong, ValidityCheckFailed
from modules.util.handlers.nginx import NginxHandlerExceededSizeLimit
from modules.util.media.downloader import Downloader, FileDownload, URLDownload

from . import *
from .flags import DownloadFlags

class Media(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot: amyrin = bot
        
    async def _process_download(self, ctx, url: str, format: str, compress: bool, include_tags: bool):
        if isinstance(ctx, discord.Interaction):
            ctx = await self.bot.get_context(ctx.message)

        if ctx.interaction:
            await ctx.interaction.response.defer()

        ctx.msg = None

        async def update(message: str):
            if ctx.interaction:
                if not ctx.interaction.response.is_done():
                    return await ctx.interaction.follow.send(message)
                return await ctx.interaction.edit_original_response(content=message)
            else:
                if not ctx.msg:
                    ctx.msg = await ctx.reply(message)
                else:
                    await ctx.msg.edit(content=message)

        nginx = self.bot.nginx

        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                downloader = Downloader(
                    ctx,
                    url,
                    output=tmp_dir,
                    nginx=nginx,
                    format=format,
                    include_tags=include_tags,
                    updater=update,
                    compress=compress
                )
            except InvalidFormat as exc:
                valid_formats = []
                for format, data in exc.valid_formats.items():
                    valid_formats.append(format)
                    for alias in data.get("aliases", []):
                        valid_formats.append(alias)

                fmt_formats = format_list(
                    valid_formats, seperator="and", brackets="`"
                )
                return await update(
                    f"Invalid format passed, valid formats are {fmt_formats}"
                )

            try:
                result = await downloader.download(
                    age_limit=18 if not ctx.channel.is_nsfw() else None
                )
            except FailedCompressionException:
                return await update(
                    "Failed to compress output file, please try running the command again in a server with a higher filesize limit (through server boosts)."
                )
            except ValidityCheckFailed as exc:
                return await update(str(exc))
            except NginxHandlerExceededSizeLimit as exc:
                limit = humanfriendly.format_size(nginx._limit, binary=True)
                size = humanfriendly.format_size(exc.size, binary=True)
                exceeded = humanfriendly.format_size(exc.exceeded, binary=True)
                return await update(f"Download ({size}) exceeds nginx server's filesize limit ({limit}) by {exceeded}.")
            except MediaException as exc:
                return await update(str(exc))
            except AgeLimited:
                return await update("This video is not able to be downloaded, as it exceeds the maximum age limit.")
            except LiveStream:
                return await update("I cannot download live streams.")
            except TooLong as exc:
                if exc.duration:
                    duration = humanfriendly.format_timespan(int(exc.duration))
                    limit = humanfriendly.format_timespan(int(exc.limit))
                    return await ctx.send(f"Video with duration {duration} exceeds the maximum limit of {limit}.")
                return await ctx.send("Unable to get duration of video, panicking.")
            except json.JSONDecodeError as exc:
                if random.randint(1,1000) == 591:
                    reason = "of gas leak!?!??!?"
                else:
                    reason = "the URL is not supported by yt-dlp."
                return await update(f"Failed to parse validity checking result. This might be because {reason}")

            compressed: bool = result.compressed
            content_type_converted: bool = result.content_type_converted
            sizes = result.sizes

            content = []

            if compressed:
                old_size = sizes.get("old")
                new_size = sizes.get("new")

                fmt_old_size = humanfriendly.format_size(old_size)
                fmt_new_size = humanfriendly.format_size(new_size)

                compressed_by = 100 * (old_size - new_size) / old_size

                compression_time = result.compression_time
                fmt_compression_time = humanfriendly.format_timespan(compression_time)

                content.append(
                    f"✅ Output compression ratio was `{int(compressed_by)}%` and the compression took {fmt_compression_time} (old: `{fmt_old_size}` | new: `{fmt_new_size}`)"
                )

            if content_type_converted:
                content.append(
                    "❗️ Mimetype of output file was different to the desired output, this might be because the file didn't contain the necessary streams for the desired output"
                )

            if isinstance(result, FileDownload):
                content = None
                attachments = [discord.File(result.path)]#
            elif isinstance(result, URLDownload):
                content = result.url
                attachments = []

            if ctx.interaction:
                await ctx.interaction.edit_original_response(
                    content=content,
                    attachments=attachments,
                )
            else:
                await ctx.msg.edit(
                    content=content,
                    attachments=attachments,
                )
            
    @command(
        commands.command,
        name="download",
        aliases=["dl"],
        description="Download a video or audio from a yt-dlp supported source.",
        examples=[
            "{prefix}download https://www.youtube.com/watch?v=gd-7Ye_vX1k"
        ],
    )
    @commands.cooldown(1, 15, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.user)
    async def download(
        self, ctx,
        url: str = commands.param(
            description="The URL for the video or audio you want to download",
            converter=URLConverter
        ),
        *, flags: DownloadFlags = None
    ):
        if flags:
            format = flags.get("format", "mp4")
            compress = flags.get("compress", False)
            include_tags = flags.get("include-tags", False)
        else:
            format = "mp4"
            compress = False
            include_tags = False
        
        await self._process_download(ctx, url, format, compress, include_tags)
        
    @commands.hybrid_command(
        name="detect",
        aliases=["shazam"],
        description="Detect a song",
    )
    async def detect(
        self, ctx,
        attachment: str = commands.param(
            default=None,
            displayed_default="any possible related attachment",
            description="URL for the attachment, not required when passing an attachment"
        )
    ):
        ctx._message = None
        
        async def update(content: str, *args, **kwargs):
            if ctx._message is None:
                ctx._message = await ctx.send(content=content, *args, **kwargs)
            else:
                await ctx._message.edit(content=content, *args, **kwargs)

        try:
            file = await FileConverter().convert(ctx, attachment)
        except TypeError as exc:
            return await update(str(exc))
        
        temp_dir = tempfile.TemporaryDirectory()

        path = None
        
        content_types = [
            "audio/aac",
            "video/x-msvideo",
            "audio/mpeg",
            "video/mp4",
            "audio/ogg",
            "audio/wav",
            "video/webm",
        ]
        
        if isinstance(file, URLObject):
            resp = await self.bot.session.head(file.url)
            
            if resp.headers.get("Content-Type") not in content_types:
                parsed_url = urlparse(file.url)
                
                valid_platforms = (
                    "tiktok.com",
                    "vm.tiktok.com",
                    "youtu.be",
                    "youtube.com",
                    "www.youtube.com"
                )
                
                if parsed_url.netloc not in valid_platforms:
                    return await update(
                        "URL doesn't have a valid content type and is not one of the supported platforms. "
                        "If this is an actual video or audio from a valid platform, please notify my developer."
                    )
                
                downloader = Downloader(
                    ctx,
                    file.url,
                    output=temp_dir.name,
                    format="mp3",
                    compress=True,
                    updater=update
                )
                    
                try:
                    download = await downloader.download()
                except MissingNginxHandler:
                    return await update("Output file is too big.")

                path = download.path
            else:
                await update(content="Downloading file...")
                path = os.path.join(temp_dir.name, "song.mp3")
                data = await file.read()
                if len(data) > 134217728:
                    return await update("File cannot be over 128MB.")
                
                await file.save(path, data=data)
        elif isinstance(file, discord.Attachment):
            await update(content="Downloading file...")
            parsed_url = urlparse(file.url)
            path = os.path.join(temp_dir.name, parsed_url.path.split("/")[-1])
            data = await file.read()
            if len(data) > 134217728:
                return await update("File cannot be over 128MB.")
                    
            await file.save(path)
            
        await update(content="Now processing request...")

        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    f"songrec audio-file-to-recognized-song \"{path}\"",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=60,
            )
        except asyncio.TimeoutError:
            return await update(
                f"Recognition took over 60 seconds and has therefore been cancelled"
            )

        stdout, _ = await proc.communicate()
        stdout = stdout.decode()
        
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return await update("Failed to parse songrec output.")

        track = data.get("track", {})

        if not track:
            return await update("Song recognition failed.")

        title = track.get("title")
        artist = track.get("subtitle")
        url = track.get("url")
        image = track.get("share", {}).get("image", None)
        genres = track.get("genres", {})
        if genres:
            formatted_genres = "\n" + textwrap.indent(
                "\n".join(
                    textwrap.indent(f"{k.title()}: {v}", "    ")
                    for k, v in genres.items()
                ),
                prefix="└─"
            )
        else:
            formatted_genres = "N/A"
        
        description = textwrap.dedent(
            f"""
**Title:** {title}
**Artist:** {artist}
**Genres:** {formatted_genres}""".strip()
        )

        embed = discord.Embed(
            title=title,
            description=description,
            url=url,
            color=self.bot.color
        )
        
        if image is not None:
            embed.set_thumbnail(url=image)
            
        await update(embed=embed, content=None)

async def setup(bot):
    await bot.add_cog(Media(bot))
