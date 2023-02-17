import inspect
import textwrap
from io import BytesIO

import discord
import humanfriendly
from discord.ext import commands

from core.bot import amyrin
from modules.util.converters import ascii_list
from modules.util.imaging.converter import ImageConverter
from modules.util.imaging.exceptions import (
    CharacterLimitExceeded,
    InvalidTemplate,
    TooManyFrames,
)
from modules.util.imaging.renderer import Renders, render
from modules.util.imaging.utils import SequentialImageProcessor

from . import *


class Updater:
    def __init__(self, context: commands.Context):
        super().__init__()
        self.ctx = context
        self.message = None

    async def __aenter__(self):
        self.message = await self.ctx.send(
            "<a:loading:1059547248259768401> Processing...", edit=False
        )
        return self

    async def __aexit__(self, _type, val, tb):
        if self.message:
            await self.message.delete()


class Imaging(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot: amyrin = bot

    async def _handle_makesweet(
        self,
        ctx: commands.Context,
        template: str,
        size: tuple[int, int],
        *images,
        **kwargs,
    ) -> None:
        async with Updater(ctx):
            try:
                result = await render(
                    Renders.makesweet, template, size, *images, **kwargs
                )
            except CharacterLimitExceeded as exc:
                return await ctx.send(
                    f"One of the given texts ({exc.length}) exceeds the maximum character limit of {exc.limit} characters"
                )

            filename = "image.gif" if result.is_animated else "image.png"
            render_time = humanfriendly.format_timespan(result.took / 1000)
            await ctx.send(
                f"Rendered in `{render_time}`",
                file=discord.File(result.buffer, filename=filename),
            )

    @command(
        name="image",
        description="Get information on a relatively available image.",
        examples=[
            "{prefix}image https://media.discordapp.net/attachments/381963689470984203/1074343125570556025/image.gif"
        ],
        aliases=["img"],
    )
    async def _image(self, ctx: commands.Context, url: str = None):
        async with Updater(ctx):
            image, _ = await ImageConverter().convert(ctx, url, fallback=False)

            processor = SequentialImageProcessor(image)
            await processor._init()
            img = processor.image
            frames = len(img.sequence)

            dimensions = f"{img.width}x{img.height}"
            colorspace = img.colorspace

            dominant_colors = (await processor.get_dominant_colors())[:6]
            dominant_colors_image = await processor.draw_dominant_colors(
                dominant_colors
            )

            buf = await processor.save()
            size = buf.read().__sizeof__()
            avg_size = size / frames

            fmt_size = humanfriendly.format_size(size)
            fmt_avg_size = humanfriendly.format_size(avg_size)
            fmt_dominant_colors = "\n".join(
                f"{i+1}: `rgb{colors}`" for i, colors in enumerate(dominant_colors)
            )
            fmt_dominant_colors = "\n".join(ascii_list(dominant_colors))
            await ctx.send(
                f"frames: `{frames}`\n"
                f"size:  `{fmt_size}` (avg per frame: `{fmt_avg_size}`)\n"
                f"dimensions: `{dimensions}`\n"
                f"colorspace: `{colorspace.upper()}`\n"
                f"dom colors: \n```{fmt_dominant_colors}```",
                file=discord.File(
                    dominant_colors_image, filename="dominant_colors.png"
                ),
            )
        await processor.close()

    @command(
        description="Add an iFunny-like caption to an image or gif",
        examples=["{prefix}caption  me when the"],
        aliases=["ifunny"],
    )
    async def caption(
        self,
        ctx: commands.Context,
        url: str = commands.param(
            description="The URL for the image, not required if an attachment is relatively available."
        ),
        *,
        text: str = commands.param(
            description="The text for the caption.", default=None
        ),
    ):
        image, used = await ImageConverter().convert(
            ctx, url, fallback=False
        )  # used variable indicates if the image derives from the argument parameter

        if image is None or not used:
            if text:
                text = url + " " + text
            else:
                text = url

            if image is None:
                image = BytesIO(
                    await ctx.author.avatar.with_size(1024).with_format("png").read()
                )
        elif image is not None and not text:
            raise commands.MissingRequiredArgument(
                inspect.Parameter("text", inspect.Parameter.KEYWORD_ONLY)
            )

        timeout = 30
        async with Updater(ctx):
            try:
                result = await asyncio.wait_for(
                    render(Renders.caption, image, text), timeout=timeout
                )
            except CharacterLimitExceeded as exc:
                return await ctx.send(
                    f"Text ({exc.length} characters) exceeds the maximum character limit of {exc.limit} characters."
                )
            except TooManyFrames as exc:
                return await ctx.send(
                    f"Image ({exc.amount} frames) exceeds the {exc.limit} frame limit."
                )
            except asyncio.TimeoutError:
                return await ctx.send(
                    f"Captioning task exceeded the maximum time of {timeout} seconds and has therefore been cancelled."
                )

            filename = "image." + ("gif" if result.is_animated else "png")
            render_time = humanfriendly.format_timespan(result.took / 1000)

            await ctx.send(
                content=f"Processed in `{render_time}`",
                file=discord.File(result.buffer, filename=filename),
            )

    @command(
        description="Render the dead heartlocket meme.",
        examples=["{prefix}heartlocket 799231501970833410 amyrin my beloved"],
        aliases=[
            "heartpendant",
            "hl",
            "heartbracelet",
            "heartlavaliere",
            "heartlavalliere",
        ],
    )
    async def heartlocket(
        self,
        ctx: commands.Context,
        argument1: str = commands.param(description="Text or image"),
        *,
        argument2: str = commands.param(description="Text or image"),
    ):
        new_argument1, _ = await ImageConverter().convert(
            ctx,
            argument1,
            relative=False,
            animated=False,
            fallback=False,
            allow_emojis=False,
        )
        new_argument2, _ = await ImageConverter().convert(
            ctx,
            argument2,
            relative=False,
            animated=False,
            fallback=False,
            allow_emojis=False,
        )

        new_argument1 = new_argument1 or argument1
        new_argument2 = new_argument2 or argument2

        await self._handle_makesweet(
            ctx, "heart-locket", (512, 512), new_argument1, new_argument2
        )

    @command(
        description="Render a waving flag with an image or text.",
        examples=[
            "{prefix}flag https://upload.wikimedia.org/wikipedia/commons/thumb/0/05/US_flag_51_stars.svg/2560px-US_flag_51_stars.svg.png"
        ],
    )
    async def flag(
        self,
        ctx: commands.Context,
        *,
        argument: str = commands.param(description="Text or image"),
    ):
        new_argument, _ = await ImageConverter().convert(
            ctx, argument, relative=False, animated=False, fallback=False
        )

        new_argument = new_argument or argument

        await self._handle_makesweet(ctx, "flag", (512, 512), new_argument)

    @command(
        description="Render a waving flag with an image or text.",
        examples=[
            "{prefix}billboard https://cdn.discordapp.com/attachments/381963689470984203/1074058719932981308/image.png"
        ],
        aliases=["billboard-cityscape"],
    )
    async def billboard(
        self,
        ctx: commands.Context,
        *,
        argument: str = commands.param(description="Text or image"),
    ):
        new_argument, _ = await ImageConverter().convert(
            ctx, argument, relative=False, animated=False, fallback=False
        )

        new_argument = new_argument or argument

        await self._handle_makesweet(
            ctx, "billboard-cityscape", (1000, 600), new_argument
        )


async def setup(
    bot,
):
    await bot.add_cog(Imaging(bot))
