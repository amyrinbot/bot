import asyncio
import functools

from discord.ext import commands


def executor(executor=None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            partial = functools.partial(func, *args, **kwargs)
            loop = asyncio.get_running_loop()
            return loop.run_in_executor(executor, partial)

        return wrapper

    return decorator


async def setup(bot: commands.Bot):
    pass
