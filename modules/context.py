import asyncio
from typing import Union
import random
import string
from io import StringIO

import discord
from discord.ext import commands
from modules.util.imaging.converter import ImageConverter
from discord.context_managers import Typing
from discord.ext.commands.context import DeferTyping

class EditTyping(Typing):
    """Custom Typing subclass to support cancelling typing when the message content changed"""
    
    def __init__(self, message: discord.Message, messageable: discord.abc.Messageable) -> None:
        self.message = message
        
        super().__init__(messageable)
        
    async def do_typing(self) -> None:
        channel = await self._get_channel()
        typing = channel._state.http.send_typing
        old_message_content = self.message.content
        
        while True:
            if old_message_content != self.message.content:
                return self.task.cancel()
            
            await asyncio.sleep(5)
            await typing(channel.id)
        
    

class Context(commands.Context):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    async def to_image(self, content: str = None):
        return await ImageConverter().convert(self, (content or self.message.content))
    
    def typing(self, *, ephemeral: bool = False) -> Union[Typing, DeferTyping]:
        if self.interaction is None:
            return EditTyping(self.message, self)
        return DeferTyping(self, ephemeral=ephemeral)

    async def send(self, content: str = None, *args, **kwargs):
        if (
            self.message.id in self.bot.command_cache.keys()
        ):
            entries = self.bot.command_cache[self.message.id]
            if len(entries) > 1:
                for message in entries[:-1]:
                    try:
                        await message.delete()
                    except discord.HTTPException:
                        pass
            func = entries[-1].edit
        else:
            func = super().send
        
        if content is not None:
            if len(content) > 2000:
                buf = StringIO()
                buf.write(content)
                buf.seek(0)
                return await func(
                    content="Message was over 2000 characters, so it has been turned into a text file",
                    file=discord.File(buf, filename="message.txt"),
                    *args,
                    **kwargs,
                )
        
        msg = await func(content=content, *args, **kwargs)
        
        if not self.bot.command_cache.get(self.message.id):
            self.bot.command_cache[self.message.id] = []
            
        self.bot.command_cache[self.message.id].append(msg)
        
        return msg
            
    async def string_to_file(
        self, content: str = None, filename: str = "message.txt"
    ) -> discord.File:
        if filename == "random":
            filename = "".join(random.choices(string.ascii_letters, k=24))

        buf = StringIO()
        buf.write(content)
        buf.seek(0)
        return discord.File(buf, filename=filename)

    async def send_as_file(
        self,
        content: str = None,
        message_content: str = None,
        filename: str = "message.txt",
        *args,
        **kwargs,
    ) -> discord.Message:

        file = self.string_to_file(content, filename=filename)

        return await super().send(
            content=message_content,
            file=file,
            *args,
            **kwargs,
        )

async def setup(bot):
    bot.context = Context
    
async def teardown(bot):
    bot.context = commands.Context