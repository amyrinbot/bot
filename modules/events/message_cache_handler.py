# credits to https://gist.github.com/EvieePy/7822af90858ef65012ea500bcecf1612

import random
import sys
import traceback

import discord
from discord.ext import commands

from core.bot import amyrin


class MessageEditHandler(commands.Cog):
    def __init__(self, bot: amyrin):
        self.bot = bot

    @commands.Cog.listener("on_message_edit")
    async def reprocess_on_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        if (
            before.content == after.content
            or after.id not in self.bot.command_cache.keys()
        ):
            return

        await self.bot.process_commands(after)

    @commands.Cog.listener("on_message_delete")
    async def purge_on_delete(self, message: discord.Message) -> None:
        if message.id not in self.bot.command_cache.keys():
            return

        entries = self.bot.command_cache[message.id]
        for message in entries:
            try:
                await message.delete()
            except discord.HTTPException:
                pass


async def setup(bot):
    await bot.add_cog(MessageEditHandler(bot))
