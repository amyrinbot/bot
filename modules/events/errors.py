# credits to https://gist.github.com/EvieePy/7822af90858ef65012ea500bcecf1612

import random
import traceback

import discord
import humanfriendly
from discord import app_commands
from discord.ext import commands
from core.bot import amyrin

class CommandErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot: amyrin = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        if hasattr(ctx.command, "on_error"):
            return

        cog = ctx.cog
        if cog:
            if cog._get_overridden_method(cog.cog_command_error) is not None:
                return

        if isinstance(error, commands.NotOwner):
            return await ctx.send("This is an owner-only command.")

        ignored = (
            commands.CommandNotFound,
            app_commands.CommandInvokeError,
            commands.CheckFailure,
        )
        error = getattr(error, "original", error)

        if isinstance(error, ignored):
            return

        elif isinstance(error, commands.NoPrivateMessage):
            try:
                await ctx.author.send(
                    f"{ctx.command} can not be used in Private Messages."
                )
            except discord.HTTPException:
                pass

        elif isinstance(error, commands.MissingRequiredArgument):
            param = error.param
            return await ctx.send(f"Missing parameter `{param.name}`", ephemeral=True)

        elif isinstance(error, commands.BadArgument):
            return await ctx.send(str(error))

        # thanks chatgpt
        elif isinstance(
            error, (app_commands.CommandOnCooldown, commands.CommandOnCooldown)
        ):
            retry_after = humanfriendly.format_timespan(round(error.retry_after, 1))
            options = [
                (
                    "Prithee, good sir or madam, 'tis requested that thou might wait a moment. "
                    "Thy command dost require a brief interlude to catch its breath. "
                    "Tarry but a short while, perchance 'twould be but {}, "
                    "then thou mayest try thy command anew. Be patient, kind soul, and all shall be well."
                ),
                (
                    "Verily, good friend, thou must grant thy command a brief respite. "
                    "Tis too hasty, and needs a moment to recover. "
                    "Wait {}, then try thy command once more. Have faith, all shall be well."
                ),
                (
                    "Hark! Thou must be patient, gentle user. "
                    "Thy command hath need of a moment's rest. "
                    "In {}, thou mayest try thy command again. "
                    "Fear not, all shall be right in the end."
                ),
                (
                    "Hold, brave user! Thy command doth require a moment of peace. "
                    "Wait {}, and then thou mayest attempt thy command once more. "
                    "Have no doubt, all shall turn out well in the end."
                ),
            ]
            msg = random.choice(options).format(retry_after)
            return await ctx.reply(msg)

        # thanks chatgpt
        elif isinstance(error, commands.MaxConcurrencyReached):
            if (
                error.per is commands.BucketType.user
                or error.per is commands.BucketType.member
            ):
                msg = (
                    "Alack and alas, good sir or madam! Thy command hath reached the maximum concurrent usage per user. "
                    "Pray, do hold thy horses and bide a moment, for the previous command must be completed ere thou mayest proceed. "
                    "Have patience, kind soul, for all shall be well in due time."
                )
            elif error.per is commands.BucketType.category:
                msg = (
                    "Good morrow, kind sir/madam. 'Tis a lamentable state of affairs, but thou hast reached the maximum concurrent commands for this category."
                    "Pray thee, wait until the previous command hath finished ere thou proceedeth with thy request. Thy patience shall be rewarded. Fare thee well!"
                )
            elif error.per is commands.BucketType.channel:
                msg = (
                    "Greetings, milord/milady. Alas, thou hast reached the utmost limit of concurrent commands per channel. "
                    "Thou must needs bide thy time until the preceding command is done, and then thou mayest make thy request anew. "
                    "Thy forbearance shall be rewarded. Fare thee well!"
                )
            elif error.per is commands.BucketType.role:
                msg = (
                    "Hail, gentle sir/madam. Verily, thou hast reached the pinnacle of concurrent commands per thy role. "
                    "Thou art requested to be patient and wait until the prior command hath come to a close. "
                    "Thy diligence shall be rewarded. Fare thee well!"
                )
            elif error.per is commands.BucketType.guild:
                msg = (
                    "Salutations, noble sir/madam. 'Tis a sorry state, but thou hast reached the zenith of concurrent commands within this guild. "
                    "Thou must needs tarry until the prior command is completed, and then thou mayest make thy request once more. "
                    "Thy steadfastness shall be rewarded. Fare thee well!"
                )
            else:
                msg = (
                    "Good day, esteemed sir/madam. Peradventure, thou hast reached the acme of concurrent commands. "
                    "Thou must exercise patience and wait until the former command is done. "
                    "Then and only then, thou may proceed with thy request. Thy perseverance shall be rewarded. Fare thee well!"
                )

            return await ctx.reply(msg)

        else:
            if await self.bot.is_owner(ctx.author):
                formatted_error = traceback.format_exception(
                    type(error), error, error.__traceback__
                )
                formatted_error = "".join(formatted_error)
                return await ctx.send(f"```py\n{formatted_error}\n```")

            result = await self.bot.db.add_error(ctx, error)
            await ctx.reply(result)


async def setup(bot):
    await bot.add_cog(CommandErrorHandler(bot))
