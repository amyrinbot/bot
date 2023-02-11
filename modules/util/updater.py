import asyncio

from discord.ext import commands


class Updater:
    def __init__(self, context: commands.Context):
        super().__init__()
        self.ctx = context
        self.message = context.message
        self.running = True
        self.loop = asyncio.get_running_loop()
        self.task = None

    async def queue(self, delay: float, coro, *args, **kwargs):
        await asyncio.sleep(delay)
        if not self.running:
            return
        return await coro(*args, **kwargs)

    async def __aenter__(self):
        self.task = self.loop.create_task(self.queue(1, self.message.add_reaction, "▶"))
        return self

    async def __aexit__(self, _type, val, tb):
        if self.task:
            self.task.cancel()
        self.running = False
        await self.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")
