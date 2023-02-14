import asyncio
from dataclasses import dataclass, field
from typing import List, Optional, Union

from discord import app_commands
from discord.ext import commands


class PermissionTemplate:
    def __init__(
        self, bot: List[str] = [], user: List[str] = [], template=None
    ) -> None:
        self.bot = bot
        self.user = user

        if template:
            self.bot += template.bot
            self.user += template.user


class PermissionTemplates:
    text_command: PermissionTemplate = PermissionTemplate(
        bot=["send_messages", "read_message_history", "send_messages_in_threads"],
        user=["send_messages", "read_message_history", "send_messages_in_threads"],
    )
    hybrid_command = PermissionTemplate = PermissionTemplate(
        template=text_command, user=["use_application_commands"]
    )


@dataclass
class CommandPermissions:
    template: Optional[PermissionTemplate] = PermissionTemplates.hybrid_command
    bot: List[str] = field(default_factory=list)
    user: List[str] = field(default_factory=list)


def command(
    func: Union[
        app_commands.command,
        commands.command,
        commands.group,
        commands.hybrid_command,
        commands.hybrid_group,
    ] = commands.hybrid_command,
    *,
    name=None,
    examples: List[str] = [],
    permissions: CommandPermissions = CommandPermissions(None, [], []),
    description="Command undocumented.",
    **kwargs
):
    cooldown_after_parsing = kwargs.pop("cooldown_after_parsing", True)

    perms = {"bot": permissions.bot, "user": permissions.user}
    if permissions.template:
        perms["bot"] += permissions.template.bot
        perms["user"] += permissions.template.user

    return func(
        name=name,
        extras={
            "permissions": {"bot": permissions.bot, "user": permissions.user},
            "examples": examples,
        },
        cooldown_after_parsing=cooldown_after_parsing,
        description=description,
        **kwargs
    )
