import random
import string
from typing import List

import discord
from discord.ext import commands

from modules.util.scraping.musixmatch import (MusixMatchScraper, SearchResult,
                                              Song, VerificationError)

from .base import View


class SongSelect(discord.ui.Select):
    def __init__(self, parent: View, results: List[SearchResult]):

        self._parent = parent
        self.texts = {}

        for song in results:
            text = f"{song.title} by {song.artist.name}"
            if text not in self.texts.keys():
                self.texts[text] = song

        super().__init__(
            placeholder="Select song",
            options=[discord.SelectOption(label=text) for text in self.texts.keys()],
        )

    async def callback(self, interaction: discord.Interaction):
        option = self.texts.get(self.values[0])
        await self._parent._callback(interaction, option)


class SongView(View):
    def __init__(self, context: commands.Context, query: str, *args, **kwargs):
        super().__init__(timeout=30, *args, **kwargs)

        self.query = query
        self.context = context
        self._scraper = None
        self._message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.context.author.id:
            await interaction.response.defer()
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True

        await self._message.edit(view=self)

    def _build_embed(self, result: Song):
        embed = discord.Embed(
            title=f"{result.title} by {result.artist.name}",
            description=f"```\n{result.lyrics}\n```",
            url=result.url,
            color=self.context.bot.color,
        )
        embed.set_thumbnail(url=result.album_cover)

        return embed

    async def _callback(self, interaction: discord.Interaction, option: SearchResult):
        await interaction.response.defer()

        async with self.context.channel.typing():
            try:
                song = await self._scraper.get_song(option.url)
            except VerificationError as exc:
                await interaction.edit_original_response(
                    embed=None, view=None, content=str(exc)
                )
            else:
                embed = self._build_embed(song)
                await interaction.edit_original_response(embed=embed, content=None)

        self._message = await interaction.original_response()

    async def start(self):
        ctx = self.context

        self._scraper = MusixMatchScraper(ctx.bot.bcontext)
        try:
            results = await self._scraper.search(self.query, lyrics_only=True)
        except VerificationError as exc:
            self._message = await ctx.send(content=str(exc))
        else:
            selection = SongSelect(self, results[:25])
            self.identifiers = selection.texts
            self.add_item(selection)

            self._message = await ctx.send(
                content="Please select the song you mean, or try to be more specific if it isn't in there",
                view=self,
            )


async def setup(bot):
    pass
