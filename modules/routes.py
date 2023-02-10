import os
from typing import Dict

from discord.ext import commands
from discord.ext.ipc.objects import ClientPayload
from discord.ext.ipc.server import Server


class Routes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        if self.bot.ipc is not None and not self.bot.ipc.started:
            await self.bot.ipc.start()

    async def cog_unload(self) -> None:
        await self.bot.ipc.stop()
        self.bot.ipc = None

    @Server.route()
    async def get_users_and_guilds(self, data: ClientPayload) -> Dict:
        await self.bot.wait_until_ready()

        users = 0

        for guild in self.bot.guilds:
            users += sum(not x.bot for x in guild.members)

        guilds = len(self.bot.guilds)
        return {"users": users, "guilds": guilds}


async def setup(bot):
    await bot.add_cog(Routes(bot))
