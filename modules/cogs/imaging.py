import inspect
from io import BytesIO
import math
import discord
from discord.ext import commands
import humanfriendly

from core.bot import amyrin
from modules.util.imaging.exceptions import CharacterLimitExceeded, TooManyFrames

from . import *
from modules.util.imaging.converter import ImageConverter
from modules.util.imaging.renderer import render, Renders


class Imaging(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot: amyrin = bot

    @command(
        description="Add an iFunny-like caption to an image or gif",
        examples=["{prefix}caption  me when the"],
        aliases=["ifunny"],
    )
    async def caption(
        self, ctx: commands.Context,
        url: str = commands.param(
            description="The URL for the image, not required if an attachment is relatively available."
        ),
        *, text: str = commands.param(
            description="The text for the caption.",
            default=None
        )
    ):
        image, used = await ImageConverter().convert(ctx, url, fallback=False) # used variable indicates if the image derives from the argument parameter
        
        if image is None or not used:
            if text:
                text = url + " " + text
            else:
                text = url
                
            if image is None:
                image = BytesIO(await ctx.author.avatar.with_size(512).read())
        elif image is not None and not text:
            raise commands.MissingRequiredArgument(inspect.Parameter("text", inspect.Parameter.KEYWORD_ONLY))
        
        timeout = 30
        try:
            async with ctx.typing():
                result = await asyncio.wait_for(
                    render(Renders.caption, image, text),
                    timeout=timeout
                )
        except CharacterLimitExceeded as exc:
            return await ctx.send(f"Text ({exc.length} characters) exceeds the maximum character limit of {exc.limit} characters.")
        except TooManyFrames as exc:
            return await ctx.send(f"Image ({exc.amount} frames) exceeds the {exc.limit} frame limit.")
        except asyncio.TimeoutError:
            return await ctx.send(f"Captioning task exceeded the maximum time of {timeout} and has therefore been cancelled.")
        
        filename = "image." + ("gif" if result.is_animated else "png")
        took = humanfriendly.format_timespan(result.took/1000)
        
        await ctx.send(
            content=f"Processed in `{took}`",
            file=discord.File(result.buffer, filename=filename)
        )        


async def setup(
    bot,
):
    await bot.add_cog(Imaging(bot))
