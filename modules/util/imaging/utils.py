from copy import copy
from io import BytesIO

from PIL import Image

from modules.util.executor import executor


@executor()
def is_animated(img: bytes | BytesIO):
    img = copy(img)

    if isinstance(img, bytes):
        img = BytesIO(img)

    with Image.open(img) as image:
        return image.is_animated
    
@executor()
def convert_image(img: bytes | BytesIO, fmt: str = "png"):
    img = copy(img)
    
    if isinstance(img, bytes):
        img = BytesIO(img)
        
    buf = BytesIO()
    with Image.open(img) as image:
        if fmt.lower() == "jpeg":
            image = image.convert("RGB")
        
        image.save(buf, fmt)
        
    buf.seek(0)
    return buf


@executor()
def resize_keep_ratio(img: bytes | BytesIO, size: tuple[int, int]) -> BytesIO:
    img = copy(img)

    if isinstance(img, bytes):
        img = BytesIO(img)

    with Image.open(img) as image:
        aspect_ratio = image.height / image.width
        new_width, new_height = size
        new_size = (new_width, int(new_height * aspect_ratio))

        image = image.resize(new_size)
        buf = BytesIO()
        image.save(buf, "PNG")
        buf.seek(0)
        return buf


@executor()
def crop_to_center(img: bytes | BytesIO) -> BytesIO:
    img = copy(img)

    if isinstance(img, bytes):
        img = BytesIO(img)

    with Image.open(img) as image:
        width, height = image.size

        left = (width - height) / 2
        top = (height - height) / 2
        right = (width + height) / 2
        bottom = (height + height) / 2

        image = image.crop((left, top, right, bottom))

        buf = BytesIO()
        image.save(buf, "PNG")
        image.close()
        buf.seek(0)
        return buf
