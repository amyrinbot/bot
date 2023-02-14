import functools
from copy import copy
from io import BytesIO
from typing import List

from PIL import Image
from wand.image import Image as WandImage

from modules.util.executor import executor


class NotInitialized(Exception):
    pass


def check_initialized(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self._initialized:
            raise NotInitialized
        else:
            return func(self, *args, **kwargs)

    return wrapper


def fit_images(imgs: List[BytesIO], width: int = 7, limit: int = None) -> BytesIO:
    images = []
    if limit is None:
        imgs = imgs
    else:
        imgs = imgs[:limit]
    for img in imgs:
        if not isinstance(img, Image.Image):
            if isinstance(img, bytes):
                img = BytesIO(img)
            img = Image.open(img)
        images.append(img.resize((128, 128)))

    _width = 0
    _height = 0
    for img in images[:width]:
        _width += 128
    for img in images[::width]:
        _height += 128

    size = _width, _height

    image = Image.new("RGBA", size)
    position = [0, 0]
    count = 0
    for img in images:
        try:
            image.paste(img, tuple(position), img)
        except ValueError:
            image.paste(img, tuple(position))
        count += 1
        if count == width:
            position[1] += 128
            position[0] = 0
            count = 0
        else:
            position[0] += 128

    for img in images:
        img.close()

    buffer = BytesIO()
    image.save(buffer, format="png")
    buffer.seek(0)
    return buffer


class SequentialImageProcessor:
    def __init__(self, image: bytes | BytesIO | WandImage, format: str = None) -> None:
        self.image: WandImage = None
        self.format = format

        self._initialized = False
        self._image = image
        self._save_kwargs = {}

    @executor()
    def _init(self) -> None:
        image = self._image
        if not isinstance(image, WandImage):
            if isinstance(image, BytesIO):
                image = image.read()

            self.image = WandImage(blob=image, format=self.format)
        else:
            self.image = image

        self._initialized = True

    async def __aenter__(self):
        pass

    async def __aexit__(self):
        if self.image:
            return await self.save()

    @executor()
    @check_initialized
    def change_format(self, fmt: str) -> None:
        if fmt.lower() == "jpeg":
            self.image.colorspace = "rgb"

        self.image.format = fmt
        self._save_kwargs["format"] = fmt

    @staticmethod
    @check_initialized
    def animated(self) -> bool:
        return len(self.image.sequence) > 1

    @executor()
    @check_initialized
    def close(self) -> None:
        self.image.close()

    @check_initialized
    def _get_dominant_colors(self) -> List[tuple[int, int, int]]:
        # thanks chatgpt for this!!
        pixel_colors = self.image.export_pixels(channel_map="RGB")

        color_counts = {}
        for i in range(0, len(pixel_colors), 3):
            color = tuple(pixel_colors[i : i + 3])
            if color not in color_counts:
                color_counts[color] = 1
            else:
                color_counts[color] += 1

        colors = sorted(color_counts, key=color_counts.get, reverse=True)
        return colors

    @executor()
    def get_dominant_colors(self) -> List[tuple[int, int, int]]:
        return self._get_dominant_colors()

    @executor()
    @check_initialized
    def draw_dominant_colors(
        self, colors: List[tuple[int, int, int]] = None
    ) -> BytesIO:
        if not colors:
            colors = self._get_dominant_colors()
        images = [Image.new("RGBA", (64, 64), color) for color in colors[:5]]
        result = fit_images(images)
        for image in images:
            image.close()
        return result

    @executor()
    @check_initialized
    def save(self) -> BytesIO:
        buffer = BytesIO()

        fmt = "png" if not self.animated else "gif"
        kwargs = dict(format=fmt)

        for kwarg, value in self._save_kwargs.items():
            kwargs[kwarg] = value

        buffer.write(self.image.make_blob(**kwargs))
        self.image.close()
        buffer.seek(0)
        return buffer

    @executor()
    @check_initialized
    def resize_keep_ratio(self, size: tuple[int, int], animated: bool = None):
        animated = animated if animated is not None else self.animated

        image = self.image
        aspect_ratio = image.height / image.width
        new_width, new_height = size
        new_size = (new_width, int(new_height * aspect_ratio))

        if animated:
            for frame in image.sequence:
                frame = frame.resize(*new_size)
        else:
            self.image = image.resize(*new_size)

        buf = BytesIO()
        image.save(buf, "PNG")
        buf.seek(0)
        return buf

    @executor()
    @check_initialized
    def invert(self, animated: bool = None):
        animated = animated if animated is not None else self.animated
        self.image.iterator_reset()
        self.image.negate()
        if animated:
            while self.image.iterator_next():
                self.image.negate()

    @executor()
    @check_initialized
    def crop_to_center(self, animated: bool = None):
        animated = animated if animated is not None else self.animated
        image = self.image

        width, height = image.size

        left = (width - height) / 2
        top = (height - height) / 2
        right = (width + height) / 2
        bottom = (height + height) / 2
        sizes = (int(left), int(top), int(right), int(bottom))

        if animated:
            for frame in image.sequence:
                frame = frame.crop(*sizes)
        else:
            self.image = image.crop(*sizes)


async def setup(bot):
    pass
