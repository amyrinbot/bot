import discord
import expr
from discord.ext import commands

from .base import View


async def start_calculator(ctx: commands.Context):
    view = CalculatorView(context=ctx)
    embed = view.build_embed()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg


class CalculatorButton(discord.ui.Button):
    def __init__(self, calculator, action: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.action = action
        self.calc = calculator

    async def callback(self, interaction: discord.Interaction):
        if self.action == "equals":
            if self.calc.field == "":
                return
            try:
                self.calc.field = str(
                    await self.calc.ctx.bot.loop.run_in_executor(
                        None, self.calc.state.evaluate, self.calc.field
                    )
                )
            except Exception as exc:
                if hasattr(exc, "friendly"):
                    exc = exc.friendly
                await interaction.message.edit(
                    embed=self.calc.build_embed(text=str(exc), language="py")
                )
                self.field = ""
            else:
                await self.calc.update(interaction=interaction)
        else:
            if self.action == "remove":
                self.calc.field = self.calc.field[:-1]
            elif self.action == "clear":
                self.calc.field = ""
            else:
                self.calc.field += self.action
            await self.calc.update(interaction=interaction)


class CalculatorView(View):
    def __init__(self, context: commands.Context):
        super().__init__(timeout=30)
        self.ctx = context
        self.field = ""
        self.message: discord.Message = None

        if context.author.id not in context.bot.expr_states:
            context.bot.expr_states[context.author.id] = expr.create_state()

        self.state: expr.state = context.bot.expr_states[context.author.id]

        self.button_map = [
            CalculatorButton(self, "(", style=discord.ButtonStyle.blurple, label="("),
            CalculatorButton(self, ")", style=discord.ButtonStyle.blurple, label=")"),
            CalculatorButton(self, "%", style=discord.ButtonStyle.blurple, label="%"),
            CalculatorButton(self, "remove", style=discord.ButtonStyle.red, label="⬅"),
            CalculatorButton(self, "clear", style=discord.ButtonStyle.red, label="C"),
            *[
                CalculatorButton(
                    self, str(i), style=discord.ButtonStyle.gray, label=str(i)
                )
                for i in range(7, 10)
            ],
            CalculatorButton(self, "-", style=discord.ButtonStyle.blurple, label="-"),
            CalculatorButton(self, "*", style=discord.ButtonStyle.blurple, label="*"),
            *[
                CalculatorButton(
                    self, str(i), style=discord.ButtonStyle.gray, label=str(i)
                )
                for i in range(4, 7)
            ],
            CalculatorButton(self, "^", style=discord.ButtonStyle.blurple, label="^"),
            CalculatorButton(self, "/", style=discord.ButtonStyle.blurple, label="/"),
            *[
                CalculatorButton(
                    self, str(i), style=discord.ButtonStyle.gray, label=str(i)
                )
                for i in range(1, 4)
            ],
            CalculatorButton(self, "+", style=discord.ButtonStyle.blurple, label="+"),
            CalculatorButton(
                self, "sqrt", style=discord.ButtonStyle.blurple, label="sqrt"
            ),
            CalculatorButton(self, "0", style=discord.ButtonStyle.gray, label="0"),
            CalculatorButton(self, ".", style=discord.ButtonStyle.gray, label="."),
            CalculatorButton(
                self, "equals", style=discord.ButtonStyle.green, label="="
            ),
            CalculatorButton(
                self, "log", style=discord.ButtonStyle.blurple, label="log"
            ),
            CalculatorButton(
                self, "sin", style=discord.ButtonStyle.blurple, label="sin"
            ),
        ]

        for i in self.button_map:
            self.add_item(i)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True

        await self.message.edit(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                f"Only {self.ctx.author} can interact with this menu.", ephemeral=True
            )
            return False
        return True

    def build_embed(self, text: str = None, language: str = "mathematica"):
        if text is None:
            text = self.field

        embed = discord.Embed(
            title="Calculator",
            description=f"```{language}\n{'​' if not text else text}```",
            color=self.ctx.bot.color,
        )
        return embed

    async def update(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return

        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed)
