import inspect
import os
import string
from dataclasses import dataclass
from typing import Any, Dict, List, TypedDict

import discord
from discord.ext import commands
from discord.ext.commands.parameters import Parameter as CommandsParameter

root = os.path.dirname(os.path.realpath(__file__))


@dataclass(unsafe_hash=True, frozen=True)
class Parameter:
    name: str
    type: Any
    visual_name: str
    description: str


@dataclass(unsafe_hash=True, frozen=True)
class CommandDocumentation:
    examples: List[str]
    usage: str
    parameters: List[Parameter]
    permissions: TypedDict("permissions", {"bot": List[str], "user": List[str]})


class DocParser:
    def __init__(self, variable_mapping: Dict[str, Any]) -> None:
        self._data: dict = None
        self._var_map = variable_mapping

    def _fill_variables(self, text: str, mapping: Dict[str, Any]):
        new_text = text

        for var, val in mapping.items():
            variable = "{" + var + "}"
            new_text = new_text.replace(variable, str(val))

        return new_text

    def dict_to_permissions(
        self, permissions: Dict[str, discord.Permissions]
    ) -> Dict[str, discord.Permissions]:
        items = {}

        for key, perms in permissions.items():
            items[key] = discord.Permissions(**{perm: True for perm in perms})

        return items

    def _get_usage(
        self, command_name: str, parameters: Dict[str, CommandsParameter]
    ) -> str:
        prefix = self._var_map["prefix"]
        text = [f"{prefix}{command_name}"]
        params = self._get_parameters(parameters=parameters)
        for param in params:
            text.append(param.visual_name)

        return " ".join(text)

    def _get_parameters(
        self, parameters: Dict[str, CommandsParameter]
    ) -> List[Parameter]:
        params = []
        for name, param in parameters.items():
            type = param.annotation.__name__
            visual_name = f"<{name}>" if param.required else f"[{name}]"
            params.append(
                Parameter(
                    name=name,
                    type=type,
                    visual_name=visual_name,
                    description=param.description,
                )
            )

        return params

    def get_documentation(self, command: commands.Command) -> CommandDocumentation:
        command_name = command.qualified_name

        usage = self._get_usage(command_name, command.clean_params)
        parameters = self._get_parameters(command.clean_params)
        examples = [
            self._fill_variables(example, self._var_map)
            for example in command.extras.get("examples", [])
        ]
        permissions = command.extras.get("permissions", {"bot": [], "user": []})

        return CommandDocumentation(
            usage=usage,
            parameters=parameters,
            examples=examples,
            permissions=permissions,
        )


async def setup(bot: commands.Bot):
    command_prefix = await bot.get_formatted_prefix()

    prefix = (
        command_prefix if command_prefix in string.punctuation else command_prefix + " "
    )
    variable_mapping = {"prefix": prefix}

    bot.docparser = DocParser(variable_mapping=variable_mapping)


async def teardown(bot: commands.Bot):
    bot.docparser = None
