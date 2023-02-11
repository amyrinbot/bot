from ast import List
from copy import copy
from io import BytesIO
from typing import Any, Optional

from PIL import Image, ImageSequence

from modules.util.executor import executor


class SequentialImageProcessor:
    def __init__(self, image: bytes | BytesIO | Image.Image, animated: bool = False) -> None:
        if not isinstance(image, Image.Image):
            if isinstance(image, bytes):
                image = BytesIO(image)

            self.image = Image.open(image)
        else:
            self.image = image

        self.animated = animated

        self._save_kwargs = {}
        self.format = "png"
        self.frames: List[set[Image.Image, int]] = []

    async def __aenter__(self):
        pass

    async def __aexit__(self):
        if self.frames or self.image:
            return await self.save()
        await self.close()

    @executor()
    def change_format(self, fmt: str) -> None:
        if fmt.lower() == "jpeg":
            self.image = self.image.convert("RGB")

        self._save_kwargs["format"] = fmt
        self.format = fmt

    @executor()
    def is_animated(self) -> bool:
        return self.image.is_animated

    @executor()
    def close(self) -> None:
        self.image.close()

    @executor()
    def save(self) -> BytesIO:
        frames = self.frames
        buffer = BytesIO()
        if frames:
            durations = [5 for _ in frames]
            if isinstance(frames, set):
                frames, durations = frames

            kwargs = dict(
                format="gif",
                save_all=True,
                append_images=None if len(frames) == 1 else frames[1:],
                duration=durations,
                loop=0,
                disposal=2,
                comment="im gay",
            )

            for kwarg, value in self._save_kwargs.items():
                kwargs[kwarg] = value

            frames[0].save(buffer, **kwargs)
        else:
            kwargs = dict(format="png", comment="im gay")

            for kwarg, value in self._save_kwargs.items():
                kwargs[kwarg] = value

            self.image.save(buffer, **kwargs)

        self.image.close()
        buffer.seek(0)
        return buffer

    @executor()
    def resize_keep_ratio(self, size: tuple[int, int], animated: bool = None):
        animated = animated if animated is not None else self.animated

        image = self.image
        aspect_ratio = image.height / image.width
        new_width, new_height = size
        new_size = (new_width, int(new_height * aspect_ratio))

        if animated:
            for frame in ImageSequence.Iterator(image):
                frame = frame.resize(new_size)
                self.frames.append(frame)
        else:
            self.image = image.resize(new_size)

        buf = BytesIO()
        image.save(buf, "PNG")
        buf.seek(0)
        return buf

    @executor()
    def crop_to_center(self, animated: bool = None):
        animated = animated if animated is not None else self.animated
        image = self.image

        width, height = image.size

        left = (width - height) / 2
        top = (height - height) / 2
        right = (width + height) / 2
        bottom = (height + height) / 2
        sizes = (left, top, right, bottom)

        if animated:
            for frame in ImageSequence.Iterator(image):
                frame = frame.crop(sizes)
                self.frames.append(frame)
        else:
            self.image = image.crop(sizes)


async def setup(bot):
    pass
