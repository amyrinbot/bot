from io import BytesIO
import json
import os
import random
import re
import string
from typing import Any, Callable, List, Optional, TypedDict

import discord
import magic
from discord.ext import commands

from .base import execute
from .exceptions import AgeLimited, MediaException, MediaServerException, MissingNginxHandler, NoPartsException, InvalidFormat, ValidityCheckFailed
from .compressor import Compressor, CompressionResult
from dataclasses import dataclass
import config
from modules.util.handlers.nginx import NginxHandler
from core.constants import *

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

class Downloader:
    def __init__(
        self,
        interaction: discord.Interaction | commands.Context,
        url: str,
        output: os.PathLike,
        nginx: NginxHandler = None,
        format: str = "mp4",
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
        out = await execute(f"yt-dlp -j -q \"{self._url}\"")
        return json.loads(out)

    async def _check_validity(self, age_limit: int = 18) -> bool:
        data = await self._extract_info()

        if age_limit:
            if data.get("age_limit", 0) >= age_limit:
                raise AgeLimited
        
        return True
    
    async def _update(self, message: str):
        if self._updater:
            return await self._updater(message)
        
    def _convert_to_content_type(self, key: str) -> str:
        conversion_map = {
            "mp4": "video/mp4",
            "mp3": "audio/mpeg"
        }
        
        return conversion_map.get(key)
        
    def _convert_from_content_type(self, key: str) -> str:
        conversion_map = {
            "video/mp4": "mp4",
            "audio/mpeg": "mp3"
        }
        
        return conversion_map.get(key)

    async def _download(self):
        cmd = ["yt-dlp"]

        def add_args(args: List[str]):
            for arg in args:
                cmd.append(arg)

        add_args(["-S", "vcodec:h264"])

        output = self._output
        if hasattr(self._output, "name") and getattr(self._output, "name") is not None:
            output = self._output.name

        name = self._generate_name()
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

        return new_path, content_type_converted
    
    async def _upload(self, path: os.PathLike) -> str:
        if self._nginx is None:
            raise MissingNginxHandler("nginx kwarg is required when using cdn")
        
        return await self._nginx.add(path)

    async def download(self, age_limit: int = 18) -> FileDownload | URLDownload:
        if not self._url_regex.match(self._url):
            raise MediaException("URL isn't a valid URL")
        
        await self._update(f"{LOADING} Checking validity")

        if (out := await self._check_validity(age_limit=age_limit)) is not True:
            raise ValidityCheckFailed(out)

        typename = (
            "video"
            if self._format == "mp4"
            else "audio"
            if self._format == "mp3"
            else "(unknown typename)"
        )

        await self._update(f"📥 Now downloading {typename}")

        path, content_type_converted = await self._download()

        stats = os.stat(path)
        fs_limit = 8388608 if not self._interaction.guild \
            else self._interaction.guild.filesize_limit

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
                sizes=sizes
            )

        return FileDownload(
            path=path,
            compressed=compressed,
            compression_time=compression_time,
            content_type_converted=content_type_converted,
            sizes=sizes
        )

async def setup(bot):
    pass