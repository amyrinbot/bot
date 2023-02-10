from datetime import datetime
from io import BytesIO
import re
import discord
import humanfriendly

from discord.ext import commands

from core.bot import amyrin
from modules.util.converters import FileConverter, URLObject
from modules.util.updater import Updater
from modules.views.song import SongView
from urllib.parse import quote_plus
from modules.views.paginator import WrapList, paginate
from modules.util.handlers.nginx import NginxHandlerExceededSizeLimit, NginxHandlerException

from . import *

URBAN_DICTIONARY_HYPERLINK_REGEX = r"\[([^\]]+)\]"
URBAN_DICTIONARY_API_URL = "https://api.urbandictionary.com/v0/define"
URBAN_DICTIONARY_URL = "https://www.urbandictionary.com/define.php?term={}"
URBAN_DICTIONARY_AUTHOR_URL = "https://www.urbandictionary.com/author.php?author={}"

class Utility(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot: amyrin = bot
    
    def _format_ud_hyperlink(self, term: str):
        formatted_term = quote_plus(term)
        return URBAN_DICTIONARY_URL.format(formatted_term)
    
    def _format_ud_text(self, text: str):
        new_text = text
        for result in re.finditer(URBAN_DICTIONARY_HYPERLINK_REGEX, text):
            start = result.start()
            end = result.end()
            term = text[start+1:end-1]
            formatted_hyperlink = self._format_ud_hyperlink(term)
            hyperlink_text = f"[{term}]({formatted_hyperlink})"
            new_text = new_text.replace(text[start:end], hyperlink_text)
                
        return new_text
    
    def _format_ud_definitions(self, definitions: List[dict]) -> List[discord.Embed]:
        embeds = []
        for definition in definitions:
            word = definition["word"]
            text = self._format_ud_text(definition["definition"])
            author = definition["author"]
            author_url = URBAN_DICTIONARY_AUTHOR_URL.format(quote_plus(author))
            example = self._format_ud_text(definition["example"])
            written_on = datetime.fromisoformat(definition["written_on"])
            permalink = definition["permalink"]
            thumbs_up = definition["thumbs_up"]
            thumbs_down = definition["thumbs_down"]
            
            description = f"{text}\n\n**Example:**\n{example}"
            embed = discord.Embed(
                url=permalink,
                title=word,
                description=description,
                timestamp=written_on,
                color=self.bot.color
            )
            embed.set_footer(text=f"\N{THUMBS UP SIGN} {thumbs_up} | \N{THUMBS DOWN SIGN} {thumbs_down}")
            embed.set_author(
                name=author,
                url=author_url
            )
            
            embeds.append(embed)
            
        return embeds
    
    @command(
        aliases=["ud", "urban"],
        description="Look up a term in the urban dictionary",
        examples=["{prefix}ud bottom"],
    )
    async def urbandictionary(
        self,
        ctx: commands.Context,
        term: str = commands.param(description="The term you want to look up"),
    ):
        resp = await self.bot.session.get(
            URBAN_DICTIONARY_API_URL,
            params={"term": term}
        )
        
        if resp.status != 200:
            return await ctx.send("Failed to get term definition")
        
        data = await resp.json()
        definitions = data["list"]
        
        if not definitions:
            return await ctx.send(f"No definitions found for term `{term}`")
        
        embeds: List[discord.Embed] = self._format_ud_definitions(definitions)
        
        await paginate(ctx, embeds, timeout=30)
                

    @command(
        description="Look up a song and it's lyrics",
        examples=["{prefix}song despacito"],
    )
    async def song(
        self,
        ctx: commands.Context,
        query: str = commands.param(description="The name of the song to look up"),
    ):
        view = SongView(ctx, query)
        await view.start()

    @command(
        commands.group,
        name="nginx",
        description="Manage my nginx server",
        examples=[
            "{prefix}nginx https://cdn.discordapp.com/attachments/381963689470984203/1068926488453332993/sQWxQyB.jpg"
        ],
        hidden=True,
        invoke_without_command=True
    )
    @commands.is_owner()
    async def nginx(
        self,
        ctx: commands.Context,
        file: str = commands.param(
            description="Parameter if using a URL. You don't need to pass this if you add an attachment to your message",
            default=None,
        ),
    ):
        await self.nginx_upload(ctx, file)

    @command(
        nginx.command,
        name="add",
        aliases=["save", "upload"],
        description="Save a file to my nginx server",
        examples=[
            "{prefix}nginx add https://cdn.discordapp.com/attachments/381963689470984203/1068926488453332993/sQWxQyB.jpg"
        ],
        hidden=True
    )
    @commands.is_owner()
    async def nginx_upload(
        self,
        ctx: commands.Context,
        file: str = commands.param(
            description="Parameter if using a URL. You don't need to pass this if you add an attachment to your message",
            default=None,
        ),
    ):
        file: URLObject = await FileConverter().convert(ctx, file)

        buffer = BytesIO(await file.read())
        
        try:
            url = await self.bot.nginx.add(buffer, filename=file.filename)
        except NginxHandlerExceededSizeLimit as exc:
            exceeded = humanfriendly.format_size(exc.exceeded)
            
            await ctx.send(f"Given file exceeds file limit by {exceeded}.")
        except NginxHandlerException as exc:
            await ctx.send(str(exc))
        else:
            await ctx.send(str(url))
            
    @command(
        nginx.command,
        name="remove",
        aliases=["delete"],
        description="Delete a file from my nginx server",
        examples=[
            "{prefix}nginx remove qtD8v7H2uBV3ceLv.jpg"
        ],
        hidden=True
    )
    @commands.is_owner()
    async def nginx_remove(
        self,
        ctx: commands.Context,
        name: str = commands.param(
            description="Name for the file"
        ),
    ):
        try:
            await self.bot.nginx.remove(name)
        except NginxHandlerExceededSizeLimit as exc:
            exceeded = humanfriendly.format_size(exc.exceeded)
            
            await ctx.send(f"Given file exceeds file limit by {exceeded}.")
        except FileNotFoundError:
            await ctx.send(f"File {name} could not be found.")
        else:
            await ctx.send(f"Successfully deleted file `{name}`.")
        
    @command(
        commands.command,
        name="wait",
        description="Literally just waits. Good for testing the `task cancel` command.",
        aliases=[
          "fIPASDHFUONAODJGInAKPÖFnASODfBNSDPGJKAODFHJSKLÖÄGNPSDHUIG"  
        ],
        examples=[
            "{prefix}wait",
            "{prefix}fIPASDHFUONAODJGInAKPÖFnASODfBNSDPGJKAODFHJSKLÖÄGNPSDHUIG"
        ],
    )
    async def wait_(
        self, ctx,
        time: int = commands.param(
            description="The time you want to wait",
            default=60,
            displayed_default="60 seconds"
        )
    ):
        async with Updater(ctx):
            await asyncio.sleep(time)
            
    @command(
        commands.group,
        name="tasks",
        aliases=["task"],
        description="Group for command task management.",
        examples=[
            "{prefix}task",
        ],
        invoke_without_command=True
    )
    async def tasks(self, ctx):
        ctx.command = self.bot.get_command("task list")
        await ctx.command(ctx)
        
    @command(
        tasks.command,
        name="list",
        description="List all command tasks running under your name.",
        examples=[
            "{prefix}task list",
        ],
    )
    async def task_list(self, ctx):
        command_tasks = [
            (name, task.get("created"))
            for name, task in self.bot.command_tasks.items()
            if task.get("user") == ctx.author.id and
            name != getattr(ctx, "_task_name", None)
        ]
        
        if not command_tasks:
            return await ctx.reply("There are no command tasks running under your name.")
        
        wrapped_tasks = WrapList(command_tasks, length=6)
    
        embeds = []
        
        for tasks in wrapped_tasks:
            embed = discord.Embed(
                title="Tasks",
                description="\n".join(
                    f"`{name}`, started at {discord.utils.format_dt(created, 'F')}"
                    for name, created in tasks
                ),
                color=self.bot.color
            )
            
            embeds.append(embed)
        
        await paginate(ctx, embeds)
        
    @command(
        tasks.command,
        name="cancel",
        description="Cancel a command task running under your name.",
        examples=[
            "{prefix}task cancel wait-51951",
        ],
    )
    async def task_cancel(
        self, ctx,
        name: str = commands.param(
            description="The name of the command task."
        )
    ):
        if name == getattr(ctx, "_task_name", None):
            return await ctx.send("You can't cancel this task.")
        
        name = name.lower()
        
        command_task = self.bot.command_tasks.get(name)
        
        if not command_task:
            return await ctx.send("This command task does not exist.")
        
        if command_task["user"] != ctx.author.id:
            return await ctx.send("This command task does not exist.")
        
        task: asyncio.Task = command_task["task"]
        
        try:
            task.cancel()
        except Exception as exc:
            return await ctx.send(f"Failed to cancel task `{name}`.")
        
        await ctx.send(f"Successfully cancelled task `{name}`.")

async def setup(bot):
    await bot.add_cog(Utility(bot))
