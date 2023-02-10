import json
import math
import random
import string
from typing import List, Optional

import discord
from discord.ext import commands

from modules.util.scraping.documentation.discord_py import (DocScraper,
                                                            SearchResults)

from modules.views.paginator import paginate
from .base import View


class DocSelectOption(discord.SelectOption):
    def __init__(self, original_name: str, *args, **kwargs) -> None:
        self.original_name = original_name

        super().__init__(*args, **kwargs)


class DocSelect(discord.ui.Select):
    def __init__(self, parent: View, results: SearchResults):

        self._parent = parent
        self.texts = {}

        for name, original_name, url, _ in results.results:
            if name not in self.texts.keys():
                self.texts[name] = url, original_name

        self._options = [
            DocSelectOption(label=name, original_name=original_name)
            for name, (_, original_name) in self.texts.items()
        ]
        super().__init__(
            placeholder="Select option",
            options=self._options,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self._parent.context.author:
            return await interaction.response.defer()

        option = discord.utils.get(self._options, label=self.values[0])
        await self._parent._callback(interaction, option)


class DocView(View):
    def __init__(
        self,
        context: commands.Context,
        scraper: DocScraper,
        query: str,
        color: int,
        *args,
        **kwargs,
    ):
        super().__init__(timeout=60 * 5, *args, **kwargs)

        self.query = query
        self.scraper = scraper
        self.context = context
        self._color = color
        self._message: discord.Embed = None
        self._current = None

    async def _callback(
        self, interaction: discord.Interaction, option: discord.SelectOption
    ):
        await interaction.response.defer()
        await self._update(interaction, option.original_name)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True

        embed: discord.Embed = self._message.embeds[0]
        embed.set_author(
            name=embed.author.name + " | Timed out", icon_url=embed.author.icon_url
        )
        await self._message.edit(view=self, embed=embed)

    """async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        if interaction.response.is_done():
            func = interaction.followup.send
        else:
            func = interaction.response.send_message
        return await func(
            "Unknown error occured while scraping, maybe the sphinx inventory parser returned an invalid element",
            ephemeral=True
        )"""

    async def _send(
        self, interaction: discord.Interaction | commands.Context, *args, **kwargs
    ) -> Optional[discord.Message]:
        if isinstance(interaction, commands.Context):
            self._message = await interaction.send(*args, **kwargs)
        elif isinstance(interaction, discord.Interaction):
            if interaction.response.is_done():
                await interaction.edit_original_response(*args, **kwargs)
            else:
                await interaction.response.send_message(*args, **kwargs)

            self._message = await interaction.original_response()

    async def _update(
        self, interaction: discord.Interaction | commands.Context, name: str
    ):
        update = None

        if isinstance(interaction, commands.Context):
            self._message: discord.Message = None

            async def update(text: str):
                if self._message:
                    await self._message.edit(content=text)
                elif isinstance(interaction, discord.Interaction):
                    if interaction.response.is_done():
                        await interaction.response.send_message(text)
                        self._message = await interaction.original_response()
                    else:
                        self._message = await interaction.followup.send(text, wait=True)
                elif isinstance(interaction, commands.Context):
                    self._message = await interaction.send(text)
                    
                return self._message

        docs = await self.scraper.get_documentation(name, updater=update)

        if docs is None:
            return

        examples_button: discord.ui.Button = discord.utils.get(
            self.children, custom_id="show_ex"
        )
        if examples_button:
            examples_button.disabled = not bool(docs.examples)
            
        attributes_button: discord.ui.Button = discord.utils.get(
            self.children, custom_id="show_attr"
        )
        if attributes_button:
            attributes_button.disabled = not bool(docs.attributes)

        self._current = docs

        embed = docs.to_embed(color=self._color)

        if getattr(interaction, "_message", None) is not None:
            return await interaction._message.edit(content=None, embed=embed, view=self)
        else:
            return await self._send(interaction, embed=embed, view=self)
    
    async def show_attributes(self, interaction: discord.Interaction) -> None:
        if not self._current:
            return await interaction.response.send_message(
                "Current variable is somehow empty, so attributes aren't loaded",
                ephemeral=True,
            )

        if not self._current.attributes:
            return await interaction.response.send_message(
                "There are no attributes available for this option, "
                "please report this to my developer if there are.",
                ephemeral=True,
            )
        
        def format_attribute(name: str, url: str):
            return f"[{name}]({url})"
        
        def comprehend_attributes(attributes: List[str]) -> str:
            formatted_attributes = [format_attribute(name, url) for name, url in attributes]
            return "\n".join(f"> {attribute}" for attribute in formatted_attributes[:limit])
        
        embeds = []
        
        for name, attributes in self._current.attributes.items():
            limit = 4096 # maximum embed description limit
            attrs = []
            
            for attribute in attributes:
                if not attrs:
                    attrs.append([])
                new_attrs = attrs[-1] + [attribute]
                new_text = comprehend_attributes(new_attrs)
                if len(new_text) > limit:
                    attrs.append([])
                attrs[-1].append(attribute)
                
            for attrs in attrs:
                embed = discord.Embed(
                    title=name.title(),
                    description="\n".join(format_attribute(name, url) for name, url in attrs)
                )
                embeds.append(embed)
            
        await paginate(interaction, embeds=embeds, ephemeral=True)
        #await interaction.response.send_message(embed=embed, ephemeral=True)

    async def show_examples(self, interaction: discord.Interaction) -> None:
        if not self._current:
            return await interaction.response.send_message(
                "Current variable is somehow empty, so examples aren't loaded",
                ephemeral=True,
            )

        if not self._current.examples:
            return await interaction.response.send_message(
                "There are no examples available for this option, "
                "please report this to my developer if there are.",
                ephemeral=True,
            )
            
        def build_embed(example):
            return discord.Embed(
                title="Examples",
                description=f"```py\n{example}\n```",
                color=self._color,
            )
            
        embeds = [build_embed(example) for example in self._current.examples]

        await paginate(interaction, embeds, ephemeral=True)

    async def start(self):
        ctx = self.context

        results = await self.scraper.search(self.query, limit=25, exclude_std=True)

        if not results:
            await self._send(ctx, content="No results found")

        select = DocSelect(self, results)
        
        example_button = discord.ui.Button(
            label="Show Examples", custom_id="show_ex", style=discord.ButtonStyle.grey
        )
        example_button.callback = self.show_examples
        
        attributes_button = discord.ui.Button(
            label="Show Attributes", custom_id="show_attr", style=discord.ButtonStyle.grey
        )
        attributes_button.callback = self.show_attributes
        
        self.add_item(select)
        self.add_item(example_button)
        self.add_item(attributes_button)

        await self._update(ctx, results.results[0][1])


async def setup(bot):
    pass
