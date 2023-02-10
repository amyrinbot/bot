from io import BytesIO
from modules.util.executor import executor
from PIL import Image
from copy import copy


@executor()
def is_animated(img: bytes | BytesIO):
    img = copy(img)
    
    if isinstance(img, bytes):
        img = BytesIO(img)
        
    with Image.open(img) as image:
        return image.is_animated