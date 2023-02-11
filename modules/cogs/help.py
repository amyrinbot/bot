import random
from copy import copy
from typing import List, Optional

import discord
import humanfriendly
from discord.ext import commands

from modules.util.converters import format_list

from . import PermissionTemplates


class _HelpCommand(commands.HelpCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_command_signature(self, command, group_main=None):
        if group_main is not None:
            return f"{self.context.prefix}{group_main}{command.qualified_name} {command.signature}"
        else:
            return f"{self.context.prefix}{command.qualified_name} {command.signature}"

    def get_ending_note(self):
        return (
            "❗ App (slash) commands are not listed here\n"
            f"📝 Use {self.context.prefix}{self.invoked_with} [command]"
            "📝 for more info on a command"
        )

    def _can_view(self, command: commands.Command):
        if self.context.bot.sync_is_owner(self.context.author):
            return True
        return not command.hidden

    async def send_bot_help(self, mapping, used=None):
        if used:
            self.mapping = mapping

        em = discord.Embed(
            description=self.get_ending_note(), color=self.context.bot.color
        )

        em.set_author(
            name=self.context.bot.user.name, icon_url=self.context.bot.user.avatar.url
        )

        cogs: List[commands.Command] = [
            c
            for c in self.context.bot.cogs.values()
            if any(self._can_view(x) for x in c.get_commands())
            and len(c.get_commands()) > 0
        ]

        fmt_cmds = sorted(
            cogs, key=lambda x: len(list(x.walk_commands())), reverse=True
        )

        if cogs:
            for cog in fmt_cmds:
                cmds = [
                    command
                    for command in list(cog.walk_commands())
                    if self._can_view(command)
                ]
                value = "\n".join(
                    f"• **{command.qualified_name}**" for command in cmds[:4]
                )
                if len(cmds) > 4:
                    value += "..."
                em.add_field(
                    name=f"{cog.qualified_name} [{len(cmds)}]",
                    value=value,
                    inline=True,
                )

        channel = self.get_destination()
        await channel.send(embed=em)

    async def send_cog_help(self, cog):
        channel = self.get_destination()

        if not cog.get_commands():
            return await channel.send("This cog is empty.")

        cmds = [cmd for cmd in cog.get_commands() if self._can_view(cmd)]

        if not cmds:
            await channel.send("You don't have permission to view this cog.")

        em = discord.Embed(
            title=f"{cog.qualified_name} commands [{len(cmds)}]",
            description=f"{cog.description}\n\n> "
            + ", ".join(f"`{cmd.name}`" for cmd in cmds),
            color=self.context.bot.color,
        )
        await channel.send(embed=em)

    async def send_group_help(self, group):
        channel = self.get_destination()
        if (
            not await self.context.bot.is_owner(self.context.author)
            and group.hidden is True
        ):
            return await channel.send("You do not have permission to view this group")

        documentation = self.context.bot.docparser.get_documentation(group)

        group_bucket = group._buckets
        group_cooldown = group_bucket._cooldown
        if group_cooldown is not None:
            cooldown_type = cooldown_type = list(
                commands.BucketType.user
                if group_bucket._type is commands.BucketType.default
                else group_bucket._type
            )[0]
            cooldown_per = humanfriendly.format_timespan(group_cooldown.per)
            cooldown_rate = group_cooldown.rate
            cooldown_msg = f"{''.join(f'{cooldown_rate} time' if str(cooldown_rate) == '1' else f'{cooldown_rate} times')} every {cooldown_per} per {cooldown_type}"
        else:
            cooldown_msg = "This command group has no cooldown"

        em = discord.Embed(
            title=group.name,
            description=group.description,
            color=self.context.bot.color,
        )

        em.add_field(
            name="Usage",
            value=self.get_command_signature(group, group_main=group.full_parent_name),
            inline=False,
        )

        if documentation.permissions != {"bot": [], "user": []}:
            em.add_field(
                name="Permissions",
                value="\n".join(
                    f"{name}: {', '.join(permission.replace('_', ' ').title() for permission in permissions)}"
                    for name, permissions in documentation.permissions.items()
                ),
                inline=False,
            )

        if documentation.examples:
            em.add_field(
                name="Examples",
                value="\n".join(
                    f"```\n{example}\n```" for example in documentation.examples
                ),
                inline=False,
            )

        if documentation.parameters:
            em.add_field(
                name="Parameters",
                value="\n".join(
                    f"{parameter.name} ({parameter.type}): {parameter.description}"
                    for parameter in documentation.parameters
                ),
                inline=False,
            )

        em.add_field(name="Cooldown", value=cooldown_msg, inline=False)

        if len(group.aliases) > 0:
            em.add_field(
                name=f"Aliases [{len(group.aliases)}]",
                value="> " + ", ".join(f"`{alias}`" for alias in group.aliases),
                inline=False,
            )

        if len(group.commands) > 0:
            em.add_field(
                name=f"Subcommands [{len(group.commands)}]",
                value="> "
                + ", ".join(
                    f"`{cmd.name}`" for cmd in group.commands if self._can_view(cmd)
                ),
                inline=False,
            )

        em.add_field(name="Cog", value=group.cog_name)

        await channel.send(embed=em)

    async def send_error_message(self, error):
        pass

    async def command_not_found(self, string):
        items = {}
        items.update(
            {i.qualified_name.lower(): i for i in self.context.bot.walk_commands()}
        )
        items.update({k.lower(): v for k, v in self.context.bot.cogs.items()})
        exists = items.get(string.lower())

        if exists:
            return await self.context.send_help(exists)
        else:
            return await self.context.send(
                f'❌ No command or cog called "{string}" found.'
            )

    async def command_callback(
        self, ctx: commands.Context, /, *, command: Optional[str] = None
    ) -> None:
        """
        base command_callback function but made case insensitive
        """

        await self.prepare_help_command(ctx)

        bot: commands.Bot = ctx.bot

        if command is None:
            mapping = self.get_bot_mapping()
            return await self.send_bot_help(mapping)

        cog = discord.utils.find(lambda x: x[0].lower() == command, bot.cogs.items())
        if cog is not None:
            return await self.send_cog_help(cog[1])

        maybe_coro = discord.utils.maybe_coroutine

        keys = command.split(" ")
        cmd = bot.all_commands.get(keys[0].lower())
        if cmd is None:
            string = await maybe_coro(
                self.command_not_found, self.remove_mentions(keys[0])
            )
            return await self.send_error_message(string)

        for key in keys[1:]:
            try:
                found = cmd.all_commands.get(key)  # type: ignore
            except AttributeError:
                string = await maybe_coro(
                    self.subcommand_not_found, cmd, self.remove_mentions(key)
                )
                return await self.send_error_message(string)
            else:
                if found is None:
                    string = await maybe_coro(
                        self.subcommand_not_found, cmd, self.remove_mentions(key)
                    )
                    return await self.send_error_message(string)
                cmd = found

        if isinstance(cmd, commands.Group):
            return await self.send_group_help(cmd)
        else:
            return await self.send_command_help(cmd)

    async def send_command_help(self, command):
        channel = self.get_destination()
        if (
            not await self.context.bot.is_owner(self.context.author)
            and command.hidden is True
        ):
            return await channel.send("You do not have permission to view this command")

        documentation = self.context.bot.docparser.get_documentation(command)

        command_bucket = command._buckets
        command_cooldown = command_bucket._cooldown
        if command_cooldown is not None:
            cooldown_type = list(
                commands.BucketType.user
                if command_bucket._type is commands.BucketType.default
                else command_bucket._type
            )[0]
            cooldown_per = humanfriendly.format_timespan(command_cooldown.per)
            cooldown_rate = command_cooldown.rate
            cooldown_msg = f"{''.join(f'{cooldown_rate} time' if str(cooldown_rate) == '1' else f'{cooldown_rate} times')} every {cooldown_per} per {cooldown_type}"
        else:
            cooldown_msg = "This command has no cooldown"

        em = discord.Embed(
            title=command.name,
            description=command.description,
            color=self.context.bot.color,
        )

        em.add_field(
            name="Usage",
            value=self.get_command_signature(
                command, group_main=command.full_parent_name
            ),
        )

        if documentation.permissions != {"bot": [], "user": []}:
            em.add_field(
                name="Permissions",
                value="\n".join(
                    f"{name}: {', '.join(permission.replace('_', ' ').title() for permission in permissions)}"
                    for name, permissions in documentation.permissions.items()
                ),
                inline=False,
            )

        if documentation.examples:
            em.add_field(
                name="Examples",
                value="\n".join(
                    f"```\n{example}\n```" for example in documentation.examples
                ),
                inline=False,
            )

        if documentation.parameters:
            em.add_field(
                name="Parameters",
                value="\n".join(
                    f"{parameter.name} ({parameter.type}): {parameter.description}"
                    for parameter in documentation.parameters
                ),
                inline=False,
            )

        em.add_field(name="Cooldown", value=cooldown_msg, inline=False)

        if len(command.aliases) > 0:
            em.add_field(
                name=f"Aliases [{len(command.aliases)}]",
                value="> " + ", ".join(f"`{alias}`" for alias in command.aliases),
                inline=False,
            )

        em.add_field(name="Cog", value=command.cog_name)

        await channel.send(embed=em)


class HelpCommand(commands.Cog):
    def __init__(self, bot, help_command):
        self._original_help_command = bot.help_command
        bot.help_command = help_command(
            command_attrs={
                "hidden": True,
                "aliases": ["commands"],
                "description": "Get help on certain cogs, groups or commands",
                "extras": {
                    "permissions": {
                        "bot": [
                            "send_messages",
                            "read_message_history",
                            "send_messages_in_threads",
                        ],
                        "user": [
                            "send_messages",
                            "read_message_history",
                            "send_messages_in_threads",
                        ],
                    }
                },
            }
        )
        bot.help_command.cog = self

    def cog_unload(self):
        self.context.bot.help_command = self._original_help_command


async def setup(bot):
    await bot.add_cog(HelpCommand(bot, _HelpCommand))
