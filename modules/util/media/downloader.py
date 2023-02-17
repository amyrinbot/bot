import inspect
import json
import os
import random
import re
import string
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Any, Callable, List, Optional, TypedDict

import discord
import eyed3
import magic
from discord.ext import commands

from core.bot import amyrin
from core.constants import *
from modules.util.handlers.nginx import NginxHandler
from modules.util.imaging.utils import SequentialImageProcessor

from .base import execute
from .compressor import CompressionResult, Compressor
from .exceptions import (AgeLimited, InvalidFormat, LiveStream, MediaException,
                         MissingNginxHandler, NoPartsException, TooLong)


@dataclass(frozen=True)
class FileDownload:
    path: os.PathLike
    compressed: bool
    compression_time: Optional[int]
    content_type_converted: bool
    sizes: TypedDict("sizes", {"old": int, "new": int})


@dataclass(frozen=True)
class URLDownload:
    url: str
    compressed: bool
    compression_time: Optional[int]
    content_type_converted: bool
    sizes: TypedDict("sizes", {"old": int, "new": int})


# thanks chatgpt
def format_duration(duration_ms):
    total_seconds = duration_ms // 1000
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    milliseconds = duration_ms % 1000
    if hours > 0:
        return "{:d}:{:02d}:{:02d}.{:03d}".format(hours, minutes, seconds, milliseconds)
    else:
        return "{:d}:{:02d}.{:03d}".format(minutes, seconds, milliseconds)


async def parse_subtitles(data: dict) -> str:
    lines: List[str] = []

    events = data.get("events")
    for event in events:
        start_ms = event.get("tStartMs")
        end_ms = start_ms + event.get("dDurationMs")

        start = format_duration(start_ms)
        end = format_duration(end_ms)

        for seg in event.get("segs"):
            for value in seg.values():
                for line in value.splitlines():
                    lines.append(f"[{start}-{end}]{line}")

    return lines


class Downloader:
    def __init__(
        self,
        interaction: discord.Interaction | commands.Context,
        url: str,
        output: os.PathLike,
        nginx: NginxHandler = None,
        format: str = "mp4",
        include_tags: bool = False,
        compress: bool = False,
        close_after: bool = False,
        verbose: bool = False,
        updater: Callable = None,
    ) -> None:
        self._url_regex = re.compile(
            r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)"
        )

        self.formats = {
            "mp4": {"aliases": ["video"]},
            "mp3": {"aliases": ["audio", "sound"]},
        }

        self._interaction = interaction
        self._url = url
        self._format = format.lower()
        self._compress = compress
        self._output = output
        self._close_after = close_after
        self._verbose = verbose
        self._updater = updater
        self._nginx = nginx
        self._include_tags = include_tags

        self._client: amyrin = getattr(
            self._interaction, "client", getattr(self._interaction, "bot")
        )

        aliases = {}

        for name, data in self.formats.items():
            for alias in data.get("aliases", []):
                aliases[alias] = name

        for alias, name in aliases.items():
            if self._format == alias:
                self._format = name

        if self._format not in self.formats:
            raise InvalidFormat(self.formats)

    def _debug(self, input: Any):
        if not isinstance(input, str):
            input = str(input)

        if self._verbose:
            print(input)

    def _generate_name(
        self, letters: bool = True, digits: bool = False, punctuation: bool = False
    ):
        input = []

        if letters is False and digits is False and punctuation is False:
            raise NoPartsException

        if letters is True:
            input = input + list(string.ascii_letters)

        if digits is True:
            input = input + list(string.digits)

        if punctuation is True:
            input = input + list(string.punctuation)

        return "".join(random.choices(string.ascii_letters, k=12))

    async def _extract_info(self) -> dict:
        out = await execute(f'yt-dlp -j "{self._url}"')
        print(out)
        return json.loads(out)

    async def _check_validity(self, age_limit: int = 18) -> bool:
        data = await self._extract_info()

        with open("data.json", "w") as f:
            f.write(json.dumps(data, indent=4))

        if data.get("is_live") is True:
            raise LiveStream

        duration_limit = 3600
        duration = data.get("duration")
        if (
            duration or duration_limit + 1
        ) > duration_limit:  # error if the key doesnt exist lmao
            raise TooLong(duration, duration_limit)

        if age_limit:
            if data.get("age_limit", 0) >= age_limit:
                raise AgeLimited

        return data

    async def _update(self, message: str):
        if self._updater:
            return await self._updater(message)

    def _convert_to_content_type(self, key: str) -> str:
        conversion_map = {"mp4": "video/mp4", "mp3": "audio/mpeg"}

        return conversion_map.get(key)

    def _convert_from_content_type(self, key: str) -> str:
        conversion_map = {"video/mp4": "mp4", "audio/mpeg": "mp3"}

        return conversion_map.get(key)

    async def _tag_audio_file(self, data: dict, path: os.PathLike) -> None:
        audio = eyed3.load(path)
        title = data.get("fulltitle", data.get("title", "N/A"))
        channel = data.get("channel", "N/A")
        audio.tag.title = title
        audio.tag.artist = channel

        if upload_date := data.get("upload_date"):
            date_format = "%Y%m%d"
            date = datetime.strptime(upload_date, date_format)
            audio.tag.recording_date = date.year

        if subtitles := data.get("subtitles"):
            for name, subtitles in subtitles.items():
                if not name.startswith("en") or not subtitles:
                    continue

                subtitle = subtitles[0]
                url = subtitle.get("url")
                async with self._client.session.get(url) as resp:
                    if resp.status != 200:
                        continue

                    subtitles = await resp.json()
                    parsed_subtitles = await parse_subtitles(subtitles)
                    audio.tag.lyrics.set(
                        "\n".join(parsed_subtitles), "Synchronized lyrics", b"eng"
                    )

        if thumbnails := data.get("thumbnails"):
            thumbnail = thumbnails[-1].get("url")
            if thumbnail:
                async with self._client.session.get(thumbnail) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get("Content-Type", "image/jpeg")
                        imagedata = await resp.read()

                        processor = SequentialImageProcessor(imagedata)
                        await processor._init()
                        await processor.resize_keep_ratio((300, 300))
                        await processor.crop_to_center()
                        img = await processor.save()

                        imagedata = img.read()

                        audio.tag.images.set(
                            3,
                            imagedata,
                            content_type,
                            "YouTube Thumbnail",
                        )

        audio.tag.save()

    async def _download(self, data: dict):
        cmd = ["yt-dlp"]

        def add_args(args: List[str]):
            for arg in args:
                cmd.append(arg)

        add_args(["-S", "vcodec:h264"])

        output = self._output
        if hasattr(self._output, "name") and getattr(self._output, "name") is not None:
            output = self._output.name

        name = data.get("title")
        filename = name + "." + self._format
        path = os.path.join(output, filename)
        add_args(["--output", f'"{path}"'])

        if self._format == "mp3":
            add_args(["--extract-audio", "--audio-format mp3"])
        elif self._format == "mp4":
            add_args(["-f", "mp4"])

        add_args([f'"{self._url}"'])

        fmt_cmd = " ".join(cmd)
        self._debug(fmt_cmd)

        await execute(fmt_cmd)

        if self._close_after:
            try:
                self._output.cleanup()
            except AttributeError:
                pass

        magic_file = magic.Magic(mime=True)
        file_content_type = magic_file.from_file(path)

        content_type_converted = False
        new_path = path
        if conversion := self._convert_from_content_type(file_content_type):
            last_part = path.split(".")[-1]
            if last_part != conversion:
                content_type_converted = True
                new_path = path.replace("." + last_part, "." + conversion)
                os.rename(path, new_path)

        if self._format == "mp3" and self._include_tags:
            await self._tag_audio_file(data, new_path)

        return new_path, content_type_converted

    async def _upload(self, path: os.PathLike) -> str:
        if self._nginx is None:
            raise MissingNginxHandler("nginx kwarg is required when using cdn")

        return await self._nginx.add(path)

    async def download(self, age_limit: int = 18) -> FileDownload | URLDownload:
        if not self._url_regex.match(self._url):
            raise MediaException("URL isn't a valid URL")

        await self._update(f"{LOADING} Checking validity")

        data = await self._check_validity(age_limit=age_limit)

        typename = (
            "video"
            if self._format == "mp4"
            else "audio"
            if self._format == "mp3"
            else "(unknown typename)"
        )

        name = data.get("title")
        await self._update(f"📥 Now downloading `{name}` as `{typename}`.")

        path, content_type_converted = await self._download(data)

        stats = os.stat(path)
        fs_limit = (
            8388608
            if not self._interaction.guild
            else self._interaction.guild.filesize_limit
        )

        compressed = False
        new_size = None
        compression_time = None
        if stats.st_size > fs_limit and self._compress:
            await self._update(f"🛠 Now compressing {typename}")
            compressor = Compressor(
                path=path,
                target_size=fs_limit,
                format=self._format,
                tempdir=self._output,
                verbose=self._verbose,
            )

            data: CompressionResult = await compressor.compress()
            path = data.path
            compression_time = data.compression_time

            new_size = data.sizes["old"]
            compressed = True

        sizes = {"old": stats.st_size, "new": new_size}

        if (new_size or stats.st_size) > fs_limit:
            url = await self._upload(path)

            return URLDownload(
                url=url,
                compressed=compressed,
                compression_time=compression_time,
                content_type_converted=content_type_converted,
                sizes=sizes,
            )

        return FileDownload(
            path=path,
            compressed=compressed,
            compression_time=compression_time,
            content_type_converted=content_type_converted,
            sizes=sizes,
        )


async def setup(bot):
    pass
