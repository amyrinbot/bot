from discord.ext import commands


class PullFlags(commands.FlagConverter, delimiter=" ", prefix="--"):
    reload: bool = False
    restart: bool = False
