from typing import Iterable, List

import discord
from discord.ext import commands

from .base import View


async def paginate(
    ctx: commands.Context | discord.Interaction,
    embeds: List,
    timeout: int = 30,
    emojis: dict = None,
    index: int = None,
    page_count: int = None,
    *args,
    **kwargs,
):
    return await EmbedPaginator(embeds, emojis, index, page_count).start(
        ctx, timeout=timeout, *args, **kwargs
    )


def cut_text(text: str, length: int) -> str:
    if len(text) > length:
        return text[: length - 3] + "..."
    return text


def cut_iterable(iterable: Iterable, length: int, attribute: str = None) -> str:
    if len(iterable) > length:
        return ", ".join(iterable[:length]) + ", ..."
    return ", ".join(iterable)


def WrapList(list_: list, length: int):
    def chunks(seq, size):
        for i in range(0, len(seq), size):
            yield seq[i : i + size]

    return list(chunks(list_, length))


class EmbedPaginator:
    def __init__(
        self,
        embeds: List,
        emojis: dict = None,
        index: int = None,
        page_count: int = None,
    ):
        self.embeds = embeds
        self.emojis = emojis or {
            "fullleft": "⏪",
            "left": "◀",
            "right": "▶",
            "fullright": "⏩",
        }
        self.page_count = page_count
        self.visual_index = index

        self.page = embeds[0]
        self.index = 0
        self.message: discord.Message = None
        self.context: commands.Context = None

        self.buttons = {
            "fullleft": discord.ui.Button(
                style=discord.ButtonStyle.grey,
                emoji=self.emojis.get("fullleft"),
                disabled=True,
            ),
            "left": discord.ui.Button(
                style=discord.ButtonStyle.grey,
                emoji=self.emojis.get("left"),
                disabled=True,
            ),
            "middle": discord.ui.Button(
                style=discord.ButtonStyle.blurple, label=self.middle
            ),
            "right": discord.ui.Button(
                style=discord.ButtonStyle.grey, emoji=self.emojis.get("right")
            ),
            "fullright": discord.ui.Button(
                style=discord.ButtonStyle.grey, emoji=self.emojis.get("fullright")
            ),
        }

        self.update_buttons()

    @property
    def pages(self):
        return len(self.embeds)

    @property
    def author(self):
        if self.context is None:
            return None
        if isinstance(self.context, discord.Interaction):
            return self.context.user
        return self.context.author

    def middle(self, index: int = None, pages: int = None):
        if self.visual_index is not None:
            index = self.visual_index + self.index
        elif index is None:
            index = self.index + 1

        if pages is None:
            pages = self.page_count or self.pages
        return f"{index}/{pages}"

    def new_view(self, timeout: int = 30):
        _self = self

        class NewView(View):
            def __init__(self, timeout: int):
                super().__init__(timeout=timeout)

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user != _self.author:
                    await interaction.response.send_message(
                        f"Only {_self.author} can use these buttons.", ephemeral=True
                    )
                    return False
                return True

            async def on_timeout(self) -> None:
                await self.disable_all(_self.message)

            @discord.ui.button(
                custom_id=_self.buttons["fullleft"].custom_id,
                disabled=_self.buttons["fullleft"].disabled,
                emoji=_self.buttons["fullleft"].emoji,
                label=_self.buttons["fullleft"].label,
                style=_self.buttons["fullleft"].style,
            )
            async def fullleft(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                await _self.fullleft(interaction)

            @discord.ui.button(
                custom_id=_self.buttons["left"].custom_id,
                disabled=_self.buttons["left"].disabled,
                emoji=_self.buttons["left"].emoji,
                label=_self.buttons["left"].label,
                style=_self.buttons["left"].style,
            )
            async def left(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                await _self.left(interaction)

            @discord.ui.button(
                custom_id=_self.buttons["middle"].custom_id,
                disabled=_self.buttons["middle"].disabled,
                emoji=_self.buttons["middle"].emoji,
                label=_self.buttons["middle"].label,
                style=_self.buttons["middle"].style,
            )
            async def middle(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                if _self.message is not None:
                    await _self.message.delete()

            @discord.ui.button(
                custom_id=_self.buttons["right"].custom_id,
                disabled=_self.buttons["right"].disabled,
                emoji=_self.buttons["right"].emoji,
                label=_self.buttons["right"].label,
                style=_self.buttons["right"].style,
            )
            async def right(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                await _self.right(interaction)

            @discord.ui.button(
                custom_id=_self.buttons["fullright"].custom_id,
                disabled=_self.buttons["fullright"].disabled,
                emoji=_self.buttons["fullright"].emoji,
                label=_self.buttons["fullright"].label,
                style=_self.buttons["fullright"].style,
            )
            async def fullright(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                await _self.fullright(interaction)

        return NewView(timeout)

    def update_buttons(self):
        if self.index == 0:
            self.buttons["fullleft"].disabled = True
            self.buttons["left"].disabled = True
        else:
            self.buttons["fullleft"].disabled = False
            self.buttons["left"].disabled = False

        if self.index == self.pages - 1 or self.pages == 1:
            self.buttons["fullright"].disabled = True
            self.buttons["right"].disabled = True
        else:
            self.buttons["fullright"].disabled = False
            self.buttons["right"].disabled = False

        self.buttons["middle"].label = self.middle()

        return self.buttons

    async def update(self, index: int, interaction: discord.Interaction):
        if self.message is not None:
            self.index = index
            self.page = self.embeds[self.index]
            self.update_buttons()
            view = self.new_view()
            await interaction.response.edit_message(embed=self.page, view=view)

    async def fullleft(self, interaction: discord.Interaction):
        await self.update(0, interaction)

    async def left(self, interaction: discord.Interaction):
        await self.update(self.index - 1, interaction)

    async def right(self, interaction: discord.Interaction):
        await self.update(self.index + 1, interaction)

    async def fullright(self, interaction: discord.Interaction):
        await self.update(self.pages - 1, interaction)

    async def start(
        self,
        ctx: commands.Context | discord.Interaction,
        timeout: int = 30,
        *args,
        **kwargs,
    ):
        self.context = ctx
        view = self.new_view(timeout=timeout)

        if kwarg_view := kwargs.pop("view", None):
            for child in kwarg_view.children:
                view.add_item(child)

        kwargs = dict(embed=self.page, view=view, *args, **kwargs)

        if isinstance(ctx, commands.Context):
            self.message = await ctx.send(**kwargs)
        elif isinstance(ctx, discord.Message):
            self.message = await ctx.channel.send(**kwargs)
        elif isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(**kwargs)
            self.message = await ctx.original_response()

        return self.message
