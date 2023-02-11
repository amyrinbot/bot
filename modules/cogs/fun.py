import discord
import expr
from discord.ext import commands

from core.bot import amyrin
from modules.views.calculator import CalculatorView, start_calculator

from . import *


class Fun(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot: amyrin = bot

        self.expr_states = {}

    @command(
        description="Open calculator or calculate given expression",
        examples=["{prefix}calculator", "{prefix}calculate 1+1", "{prefix}calc 861/95"],
        aliases=["calc", "calculate", "math"],
    )
    async def calculator(
        self,
        ctx: commands.Context,
        *,
        expression: str = commands.param(
            default=None, description="The expression you want to calculate"
        ),
    ):
        if expression is None:
            return await start_calculator(ctx)

        em = discord.Embed(color=self.bot.color)
        if ctx.author.id not in self.bot.expr_states:
            self.bot.expr_states[ctx.author.id] = expr.create_state()

        state = self.bot.expr_states[ctx.author.id]

        try:
            res = await self.bot.loop.run_in_executor(None, state.evaluate, expression)
        except Exception as exc:
            if hasattr(exc, "friendly"):
                error = exc.friendly
            else:
                error = exc
            em.add_field(
                name="Input", value=f"```mathematica\n{expression}```", inline=False
            )
            em.add_field(name="Error", value=f"```py\n{str(error)}```", inline=False)
        else:
            if res is None:
                return await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")
            em.add_field(
                name="Input", value=f"```mathematica\n{expression}```", inline=False
            )
            em.add_field(name="Output", value=f"```mathematica\n{res}```", inline=False)

        await ctx.send(embed=em)


async def setup(
    bot,
):
    await bot.add_cog(Fun(bot))
