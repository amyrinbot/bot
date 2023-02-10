import importlib
import os
import pathlib
import traceback

from discord.ext import commands, tasks

from core.bot import amyrin

IGNORE_EXTENSIONS = []


def path_from_extension(extension: str) -> pathlib.Path:
    return pathlib.Path(extension.replace(".", os.sep) + ".py")


class HotReload(commands.Cog):
    """
    Cog for reloading extensions as soon as the file is edited
    """

    def __init__(self, bot: amyrin):
        self.bot = bot
        if bot.debug:
            self.hot_reload_loop.start()

    def cog_unload(self):
        self.hot_reload_loop.stop()

    @tasks.loop(seconds=1)
    async def hot_reload_loop(self):
        for extension in self.bot.module_relatives.keys():
            if extension in IGNORE_EXTENSIONS:
                continue
            path = path_from_extension(extension)
            time = os.path.getmtime(path)

            if extension not in self.bot.extensions.keys():
                continue

            try:
                if self.last_modified_time[extension] == time:
                    continue
            except KeyError:
                self.last_modified_time[extension] = time
            else:
                try:
                    await self.bot.reload_extension(extension)
                except commands.ExtensionError as exc:
                    exc = "".join(
                        traceback.format_exception(type(exc), exc, exc.__traceback__)
                    )

                    self.bot.logger.error(
                        f"Error occured loading module {extension}:\n{exc}"
                    )
                except commands.ExtensionNotLoaded:
                    continue
                else:
                    self.bot.logger.debug(f"Reloaded extension: {extension}")
                    
                    for relative, _ in filter(lambda x: extension in x[1], self.bot.module_relatives.items()):
                        await self.bot.reload_extension(relative)
                        self.bot.logger.debug(f"Reloaded {extension} relative: {relative}")
                finally:
                    self.last_modified_time[extension] = time

    @hot_reload_loop.before_loop
    async def cache_last_modified_time(self):
        self.last_modified_time = {}
        # Mapping = {extension: timestamp}
        for extension in self.bot.extensions.keys():
            if extension in IGNORE_EXTENSIONS:
                continue
            path = path_from_extension(extension)
            time = os.path.getmtime(path)
            self.last_modified_time[extension] = time


async def setup(bot):
    cog = HotReload(bot)
    await bot.add_cog(cog)
