import os
import random
import string
from io import BytesIO
from pathlib import Path

import yarl

from modules.util.executor import executor


class NginxHandlerException(Exception):
    pass


class NginxHandlerExceededSizeLimit(Exception):
    def __init__(self, size: int, exceeded: int, *args: object) -> None:
        self.size = size
        self.exceeded = exceeded

        super().__init__(*args)


class NginxHandler:
    def __init__(
        self,
        url: str,
        path: os.PathLike,
        limit: int = 128 * 1024 * 1024,  # 128 mb default limit
    ) -> None:
        self._url = yarl.URL(url)
        self._path = Path(path)
        self._limit = limit

    def _generate_filepath(self, extension: str):
        for _ in range(100):
            filename = "".join(
                random.choices(string.ascii_letters + string.digits, k=16)
            )
            filepath = (self._path / filename).with_suffix(extension)

            if not filepath.exists():
                return filepath

        raise NginxHandlerException("Could not generate filepath")

    @executor()
    def add(
        self, file: BytesIO | os.PathLike, filename: str = None, limit: int = None
    ) -> yarl.URL:
        if isinstance(file, BytesIO) and filename is None:
            raise TypeError(
                'argument "filename" is required when passing io.BytesIO object'
            )

        if limit is None:
            limit = self._limit

        if not filename:
            _, filename = os.path.split(file)
        _, extension = os.path.splitext(filename)

        filepath = self._generate_filepath(extension)

        if not isinstance(file, BytesIO):
            with open(file, "rb") as f:
                filedata = f.read()
        else:
            filedata = file.read()

        if len(filedata) > self._limit:
            exceeded = len(filedata) - self._limit
            raise NginxHandlerExceededSizeLimit(size=len(filedata), exceeded=exceeded)

        filepath.write_bytes(filedata)

        relative_path = filepath.relative_to(self._path)
        return self._url.with_path(relative_path.name)

    @executor()
    def remove(self, path: os.PathLike | Path | yarl.URL):
        if isinstance(path, yarl.URL):
            path = self._path.joinpath(path.path)

        if not isinstance(path, Path):
            path = Path(path)

        if not path.is_absolute():
            path = self._path.joinpath(path)

        if not path.exists():
            raise FileNotFoundError("No such file or directory: " + f"'{path.name}'")

        os.remove(path)
