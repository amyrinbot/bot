import importlib
import os
import re
import traceback
from typing import Dict, List, Optional

import discord
from discord.ext import commands

from .base import TrashView, View


class PullView(View):
    def __init__(self, context: commands.Context, modules: List[str]) -> None:
        self.context = context
        self.modules = modules

        super().__init__()

    async def on_error(
        self, exc: Exception, item: discord.ui.Item, interaction: discord.Interaction
    ) -> None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        await interaction.response.send_message(tb, view=TrashView(self.context.author))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.context.author.id:
            await interaction.response.defer()
            return False
        return True

    async def reload_modules(self) -> Dict[str, Optional[Exception]]:
        reloaded = {}
        for module in self.modules:
            try:
                await self.context.bot.reload_extension(module)
            except commands.ExtensionNotLoaded:
                imp = importlib.import_module(module)
                importlib.reload(imp)
                reloaded[module] = None
            except Exception as exc:
                error = traceback.format_exception(type(exc), exc, exc.__traceback__)
                reloaded[module] = "\n".join(error)
            else:
                reloaded[module] = None

        return reloaded

    @discord.ui.button(style=discord.ButtonStyle.grey, label="Reload")
    async def reload(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        res = await self.reload_modules()

        msg = "\n".join(
            f"✅ `{k}`" if not v else f"❌ `{k}`\n```{v}```" for k, v in res.items()
        )
        embed = discord.Embed(
            title="Reloaded Cogs", description=msg, color=interaction.client.color
        )
        await interaction.response.send_message(embed=embed)
        await self.disable_all(interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, label="Restart")
    async def restart(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer()
        await self.disable_all(interaction)
        await self.context.invoke("restart", self.context)
