import inspect
import math
import os
import tempfile
from dataclasses import dataclass
from io import BytesIO
from typing import Callable, List, Literal, Union

from imagetext_py import (EmojiOptions, FontDB, Paint, TextAlign, WrapStyle,
                          Writer, text_size_multiline, text_wrap)
from PIL import Image, ImageSequence

from modules.util.executor import run_blocking_func
from modules.util.imaging.exceptions import (CharacterLimitExceeded,
                                             InvalidTemplate, TooManyFrames)
from modules.util.imaging.utils import convert_image
from modules.util.media.base import execute
from modules.util.timer import Timer

font_path = os.path.join(os.getcwd(), "assets/fonts")
FontDB.SetDefaultEmojiOptions(EmojiOptions(parse_discord_emojis=True))
FontDB.LoadFromDir(font_path)


@dataclass(frozen=True)
class RenderResult:
    buffer: BytesIO
    took: int
    is_animated: bool


class Renders:
    def centered_text(
        text: str, t_size_min=5, t_size_max=75, img_width=0.95
    ) -> BytesIO:
        text_limit = 1000
        text_length = len(text)

        if text_length > text_limit:
            raise CharacterLimitExceeded(len(text), text_limit)

        font = FontDB.Query("arial-unicode-ms arabic")

        size = (512, 512)
        width, height = size
        img_width = width * img_width

        # literally have no idea how binary search works so thank you very much mr chatgpt!!!
        t_size_min = 5
        t_size_max = 75

        while t_size_min < t_size_max:
            t_size = (t_size_min + t_size_max) // 2
            wrapped_text = text_wrap(
                text,
                math.floor(img_width),
                t_size,
                font,
                wrap_style=WrapStyle.Character,
                draw_emojis=True,
            )
            _, t_height = text_size_multiline(
                wrapped_text, t_size, font, draw_emojis=True
            )

            if t_height > height:
                t_size_max = t_size - 1
            else:
                t_size_min = t_size + 1

        # t_size_min will now be the optimal font size
        t_size = t_size_min
        wrapped_text = text_wrap(
            text,
            math.floor(img_width),
            t_size,
            font,
            wrap_style=WrapStyle.Character,
            draw_emojis=True,
        )
        _, t_height = text_size_multiline(wrapped_text, t_size, font, draw_emojis=True)

        buf = BytesIO()
        with Image.new("RGBA", size, "white") as img:
            with Writer(img) as writer:
                writer.draw_text_multiline(
                    text=wrapped_text,
                    x=width / 2,
                    y=height / 2,
                    ax=0.5,
                    ay=0.5,
                    width=img_width,
                    size=t_size,
                    font=font,
                    fill=Paint.Color((0, 0, 0, 255)),
                    align=TextAlign.Center,
                    draw_emojis=True,
                )

            img.save(buf, "png")

        buf.seek(0)
        return buf, False

    async def makesweet(
        template: Literal["billboard-cityscape", "flag", "heart-locket"],
        *images: List[Union[bytes, BytesIO, str]],
    ) -> BytesIO:
        command = ["docker", "run"]

        cwd = os.getcwd()
        templates_path = os.path.join(cwd, "assets/makesweet_templates")
        template_path = os.path.join(templates_path, f"{template}.zip")

        if not os.path.isfile(template_path):
            raise InvalidTemplate(template)

        command.extend(["-v", f"{templates_path}:/share/templates"])

        td = tempfile.TemporaryDirectory()
        command.extend(["-v", f"{td.name}:/share"])

        command.extend(["jottew/makesweet"])
        command.extend(["--zip", f"templates/{template}.zip"])
        command.append("--in")

        for index, image in enumerate(images):
            if isinstance(image, str):
                image, _ = await run_blocking_func(
                    Renders.centered_text, image, img_width=0.85
                )
            else:
                image = await convert_image(image, "jpeg")

            if hasattr(image, "read"):
                image = image.read()

            image_name = f"image{index}.png"
            image_path = os.path.join(td.name, image_name)
            docker_image_path = os.path.join("/share", image_name)
            with open(image_path, "wb") as f:
                f.write(image)

            command.append(docker_image_path)

        command.extend(["--gif", "output.gif"])

        command_string = " ".join(command)

        await execute(command_string)

        output_path = os.path.join(td.name, "output.gif")
        with open(output_path, "rb") as f:
            data = BytesIO(f.read())

        return data, True

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

        font = FontDB.Query("arial-unicode-bold arabic")

        with Image.open(image) as img:
            if hasattr(img, "n_frames"):
                if img.n_frames > frame_limit:
                    raise TooManyFrames(img.n_frames, frame_limit)

            aspect_ratio = img.height / img.width
            size = (1024, int(1024 * aspect_ratio))

            processed = []
            durations = []

            width, height = size
            c_width = width * 0.95  # subjective design choice for borders
            t_size = 150

            wrapped_text = text_wrap(
                text,
                math.floor(c_width),
                t_size,
                font,
                wrap_style=WrapStyle.Character,  # can change to make faster, just wont seperately wrap characters
                draw_emojis=True,
            )
            _, t_height = text_size_multiline(
                wrapped_text, t_size, font, draw_emojis=True
            )
            c_height = int(
                t_height * 1.05
            )  # objectively looks better /j (just adds borders)
            min_height = 150

            if c_height < min_height:
                c_height = min_height  # also just a subjective design choice

            full_img_size = (
                width,
                height + c_height,
            )  # combines height of the original image and the caption image height
            caption_size = (width, c_height)

            with Image.new("RGBA", caption_size, "white") as caption:
                with Writer(caption) as writer:
                    writer.draw_text_multiline(
                        text=wrapped_text,
                        x=width / 2,
                        y=c_height / 2,  # get the center of the caption image
                        ax=0.5,
                        ay=0.5,  # define anchor points (middle)
                        width=c_width,
                        size=t_size,
                        font=font,
                        fill=Paint.Color((0, 0, 0, 255)),
                        align=TextAlign.Center,
                        draw_emojis=True,
                    )

                for frame in ImageSequence.Iterator(img):
                    if text_length > gif_char_limit and not bypass_charlimit:
                        break

                    durations.append(frame.info.get("duration", 5))
                    frame = frame.resize(size, Image.ANTIALIAS)
                    with Image.new(
                        "RGBA", full_img_size, (255, 255, 255, 0)
                    ) as full_img:
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
                    comment="im gay",
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
            result = await run_blocking_func(render, *args, **kwargs)
            if inspect.iscoroutine(result):
                result = await result
        else:
            result = await render(*args, **kwargs)

    buffer, is_animated = result

    return RenderResult(buffer, timer.time * 1000, is_animated)


async def setup(bot):
    pass
