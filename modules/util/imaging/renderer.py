import asyncio
from dataclasses import dataclass
import functools
import inspect
from io import BytesIO
import os
import math
from typing import Callable

from imagetext_py import EmojiOptions, FontDB, Paint, TextAlign, WrapStyle, Writer, text_size_multiline, text_wrap

from PIL import Image, ImageSequence

from modules.util.imaging.exceptions import CharacterLimitExceeded, TooManyFrames
from modules.util.timer import Timer

font_path = os.path.join(os.getcwd(), "assets/fonts")
FontDB.SetDefaultEmojiOptions(EmojiOptions(parse_discord_emojis=True))
FontDB.LoadFromDir(font_path)

font = FontDB.Query("arial-unicode-bold arabic")

@dataclass(frozen=True)
class RenderResult:
    buffer: BytesIO
    took: int
    is_animated: bool

class Renders:
    def caption(
        image: bytes | BytesIO, text: str, bypass_charlimit: bool = False
    ) -> BytesIO:
        """probably will reimplement in rust once ive learned it"""
        
        if isinstance(image, bytes):
            image = BytesIO(image)
            
        gif_char_limit = 1000
        char_limit = 2000
        frame_limit = 200
        text_length = len(text)
        
        if text_length > char_limit and not bypass_charlimit:
            raise CharacterLimitExceeded(text_length, char_limit)
            
        with Image.open(image) as img:
            if hasattr(img, "n_frames"):
                if img.n_frames > frame_limit:
                    raise TooManyFrames(img.n_frames, frame_limit)
            
            aspect_ratio = img.height / img.width
            size = (1024, int(1024 * aspect_ratio))
            
            processed = []
            durations = []
            
            width, height = size
            c_width = width * 0.95 # subjective design choice for borders
            t_size = 75
            
            wrapped_text = text_wrap(
                text,
                math.floor(c_width),
                t_size,
                font,
                wrap_style=WrapStyle.Character, # can change to make faster, just wont seperately wrap characters
                draw_emojis=True
            )
            _, t_height = text_size_multiline(
                wrapped_text,
                t_size,
                font,
                draw_emojis=True
            )
            c_height = int(t_height * 1.05) # objectively looks better /j (just adds borders)
            min_height = 150

            if c_height < min_height:
                c_height = min_height # also just a subjective design choice
            
            full_img_size = (width, height + c_height) # combines height of the original image and the caption image height
            caption_size = (width, c_height)
            
            with Image.new("RGBA", caption_size, "white") as caption:
                with Writer(caption) as writer:
                    writer.draw_text_multiline(
                        text=wrapped_text,
                        x=width/2, y=c_height/2, # get the center of the caption image
                        ax=0.5, ay=0.5, # define anchor points (middle)
                        width=c_width,
                        size=t_size,
                        font=font,
                        fill=Paint.Color((0, 0, 0, 255)),
                        align=TextAlign.Center,
                        draw_emojis=True
                    )
                    
                for frame in ImageSequence.Iterator(img):
                    if text_length > gif_char_limit and not bypass_charlimit:
                        break
                    
                    durations.append(frame.info.get("duration", 5))
                    frame = frame.resize(size, Image.ANTIALIAS)
                    with Image.new("RGBA", full_img_size, (255, 255, 255, 0)) as full_img:
                        full_img.paste(caption, (0, 0))
                        full_img.paste(frame, (0, c_height))
                        
                        processed.append(full_img)
                        
                caption.close()
                
                buffer = BytesIO()
                processed[0].save(
                    buffer,
                    format="gif",
                    save_all=True,
                    append_images=processed[1:],
                    duration=durations,
                    loop=0,
                    disposal=2,
                    comment="im gay"
                )
                buffer.seek(0)
                
                is_animated = len(processed) > 1
                
                for frame in processed:
                    frame.close()
                    
                del processed
                img.close()
                return buffer, is_animated

async def render(render: Callable, *args, **kwargs):
    with Timer() as timer:
        if not inspect.iscoroutinefunction(render):
            partial = functools.partial(render, *args, **kwargs)
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, partial)
            if inspect.iscoroutine(result):
                result = await result
        else:
            result = await result(*args, **kwargs)
        
    buffer, is_animated = result
        
    return RenderResult(buffer, timer.time*1000, is_animated)

async def setup(bot):
    pass
