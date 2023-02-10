from discord.ext import commands

from core.bot import amyrin

from . import *


class Nonsense(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot: amyrin = bot

    @command(
        description="command dedicated to discord user jazz#0001",
        examples=["{prefix}jazz"],
    )
    async def jazz(self, ctx: commands.Context):
        await ctx.send(
            "this is so jazz\nhttps://tenor.com/view/treisio-swixels-gif-19461367"
        )


async def setup(
    bot,
):  # remove this function or this entire file if you dont want these commands
    await bot.add_cog(Nonsense(bot))
