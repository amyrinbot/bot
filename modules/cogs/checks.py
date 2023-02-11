from discord.ext import commands

from core.bot import amyrin
import config

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
        
        if ctx.prefix in self.bot.old_prefixes:
            prefix = await self.bot.get_formatted_prefix(False)

            await ctx.reply(f"You are trying to an old prefix, my new prefix is `{prefix}`.")
            return False

        if not await self.bot.is_owner(ctx.author) and ctx.author.id not in config.ALLOWED_ON_DEBUG:
            prefix = await self.bot.get_formatted_prefix(False)

            await ctx.reply(
                "You are trying to use the debug version of the bot, which only my owner can, "
                f"the prefix of the stable version is {prefix} (ex: {prefix} help)"
            )
            return False

        return True


async def setup(bot):
    await bot.add_cog(Checks(bot))
