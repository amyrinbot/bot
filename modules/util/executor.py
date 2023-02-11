import asyncio
import functools
from typing import Callable

from discord.ext import commands


async def run_blocking_func(func: Callable, *args, **kwargs):
    partial = functools.partial(func, *args, **kwargs)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial)


def executor(executor=None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return run_blocking_func(func, *args, **kwargs)

        return wrapper

    return decorator


async def setup(bot: commands.Bot):
    pass
