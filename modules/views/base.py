from copy import copy

import discord


class View(discord.ui.View):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def disable_all(self, interaction: discord.Interaction | discord.Message):
        children = copy(self.children)
        for child in self.children:
            child.disabled = True
        try:
            if isinstance(interaction, discord.Interaction):
                if interaction.response.is_done():
                    await interaction.edit_original_response(view=self)
                else:
                    await interaction.response.edit_message(view=self)
            else:
                await interaction.edit(view=self)
        except Exception:
            pass
        return children


class TrashView(View):
    def __init__(self, author: discord.Member):
        super().__init__()
        self.author: discord.Member = author

    @discord.ui.button(
        style=discord.ButtonStyle.red, emoji="🗑", label="Delete", custom_id="delete"
    )
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return
        await interaction.message.delete()
