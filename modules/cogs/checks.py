from discord.ext import commands

import config
from core.bot import amyrin


class Checks(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot: amyrin = bot
        self.bot.add_check(self.debug_check)

    async def debug_check(self, ctx: commands.Context):
        if not self.bot.debug:
            return True

        if self.bot.debug and ctx.interaction:
            return False

        if (
            not await self.bot.is_owner(ctx.author)
            and ctx.author.id not in config.ALLOWED_ON_DEBUG
        ):
            prefix = await self.bot.get_formatted_prefix(False)

            await ctx.reply(
                "You are trying to use the debug version of the bot, which only my owner can, "
                f"the prefix of the stable version is {prefix} (ex: {prefix} help)"
            )
            return False

        return True

    async def command_is_disabled(self, ctx: commands.Context):
        disabled_commands = await self.bot.db.get_disabled_commands(ctx.guild)
        if disabled_commands and ctx.command.qualified_name in disabled_commands:
            await ctx.reply(
                f"Sorry, but that command has been disabled by the server administrators."
            )
            return False
        return True

    async def is_blacklisted(self, ctx):
        query = await self.bot.db.is_blacklisted(ctx.author)

        if query is not None:
            reason = query["reason"]
            await ctx.reply(
                f"Sorry, but you are blacklisted for reason `{reason}`, "
                f"if you think this was a mistake, please contact my developer ({self.bot.owner})."
            )
            return False
        return True


async def setup(bot):
    await bot.add_cog(Checks(bot))
