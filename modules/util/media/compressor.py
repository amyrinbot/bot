import inspect
import json
import os
import tempfile
from dataclasses import dataclass
from io import BytesIO
from typing import List, TypedDict

import discord
import mutagen

from modules.util.executor import executor
from modules.util.timer import Timer

from .base import execute
from .exceptions import FailedCompressionException


@dataclass(frozen=True)
class CompressionResult:
    path: os.PathLike
    compression_time: int
    sizes: TypedDict("sizes", {"old": int, "new": int})


class Compressor:
    def __init__(
        self,
        path: os.PathLike | discord.File | BytesIO | bytes,
        target_size: float,
        format: str = None,
        tempdir=None,
        verbose: bool = False,
    ) -> None:
        self._path = path
        self._target_size = target_size
        self._format = format
        self._original_format = format
        self._verbose = verbose
        self._tempdir = tempdir or tempfile.TemporaryDirectory()

        self._formats = {
            "video": ["mp4", "mov", "mkv", "avi"],
            "audio": ["mp3", "ogg", "wav"],
        }

        all_formats = []
        for format, formats in self._formats.items():
            all_formats.append(format)
            for lformat in formats:
                all_formats.append(lformat)

        if self._format not in all_formats:
            raise Exception("Unsupported format passed")

        for format, formats in self._formats.items():
            if self._format in formats:
                self._format = format
                break

        if self._format is None:
            if isinstance(self._path, discord.File):
                self._format = self._path.filename.split(".")[-1]
            else:
                raise Exception(
                    'Argument  "format" is required when not passing a "discord.File" as the "path" argument'
                )

    async def cleanup(self) -> None:
        if inspect.iscoroutinefunction(self._tempdir.cleanup):
            await self._tempdir.cleanup()
        else:
            self._tempdir.cleanup()

    async def _get_video_duration(self, path: os.PathLike) -> float:
        out = await execute(
            f'ffprobe -v quiet -show_streams -select_streams v:0 -of json "{path}"',
            self._verbose,
        )
        data = json.loads(out)["streams"][0]
        duration = float(data["duration"])
        return duration

    @executor()
    def _get_audio_duration(self, path: os.PathLike) -> float:
        audio = mutagen.File(path)
        return audio.info.length

    async def _convert_file_to_path(self) -> os.PathLike:
        if not isinstance(self._path, discord.File):
            raise Exception(
                'Path argument must be "discord.File" for this function to work'
            )

        tempdir = self._tempdir
        filepath = os.path.join(tempdir.name, self._path.filename)
        with open(filepath, "wb") as f:
            f.write(self._path.fp.read())

        return filepath

    async def _convert_bytesio_to_path(self) -> os.PathLike:
        if not isinstance(self._path, BytesIO):
            raise Exception(
                'Path argument must be "io.BytesIO" for this function to work'
            )

        orig_fmt = self._original_format
        tempdir = self._tempdir
        filename = (
            f"video.{orig_fmt}" if self._format == "video" else f"audio.{orig_fmt}"
        )
        filepath = os.path.join(tempdir.name, filename)
        with open(filepath, "wb") as f:
            f.write(self._path.read())

        return filepath

    async def _convert_bytes_to_path(self) -> os.PathLike:
        if not isinstance(self._path, bytes):
            raise Exception('Path argument must be "bytes" for this function to work')

        orig_fmt = self._original_format
        tempdir = self._tempdir
        filename = (
            f"video.{orig_fmt}" if self._format == "video" else f"audio.{orig_fmt}"
        )
        filepath = os.path.join(tempdir.name, filename)
        with open(filepath, "wb") as f:
            f.write(self._path)

        return filepath

    async def compress(self) -> CompressionResult:
        path = self._path
        target_size = self._target_size

        if isinstance(self._path, discord.File):
            path = await self._convert_file_to_path()
        elif isinstance(self._path, BytesIO):
            path = await self._convert_bytesio_to_path()
        elif isinstance(self._path, bytes):
            path = await self._convert_bytes_to_path()

        cmd = ["ffmpeg", "-i", path]

        def add_args(args: List[str]):
            for arg in args:
                cmd.append(arg)

        if self._format == "video":
            duration = await self._get_video_duration(path)
        elif self._format == "audio":
            duration = await self._get_audio_duration(path)

        out_size = ((target_size * 8) / duration) * 0.9

        if self._format == "mp4":
            out_size = out_size / 2
            add_args(["-b:v", str(out_size)])

        add_args(["-b:a", str(out_size)])

        last_part = path.split(".")[-1]
        output_path = path.replace(f".{last_part}", f"_compressed.{last_part}")
        add_args([output_path])

        with Timer() as timer:
            await execute(" ".join(cmd), verbose=self._verbose)

        sizes = {"old": os.stat(path).st_size, "new": os.stat(output_path).st_size}

        if os.stat(output_path).st_size > os.stat(path).st_size:
            raise FailedCompressionException(sizes)

        return CompressionResult(path=path, compression_time=timer.time, sizes=sizes)
