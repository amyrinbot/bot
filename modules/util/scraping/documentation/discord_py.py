import ast
import asyncio
import functools
import inspect
import json
import logging
import os
import re
import traceback
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, TypedDict
from urllib.parse import ParseResult, urljoin, urlparse

import discord
from bs4 import BeautifulSoup, SoupStrainer, Tag
from fuzzywuzzy import fuzz
from humanfriendly import format_timespan
from playwright._impl._api_types import TimeoutError as PlaywrightTimeoutError
from playwright.async_api._generated import Browser
from sphobjinv import DataObjStr, Inventory

from core.bot import amyrin
from core.constants import *
from modules.util.executor import executor
from modules.util.timer import Timer


class FailedCachingTask(Exception):
    def __init__(self, name: str, exception: Exception, task: asyncio.Task) -> None:
        self.name = name
        self.exception = exception
        self.task = task

class Response:
    def __bool__(self):
        return any(
            getattr(self, str(attr)) for attr in dir(self) if not attr.startswith("_")
        )


@dataclass(frozen=True)
class RTFSItem:
    name: str
    url: str


class RTFSResults:
    def __init__(self, results: set[str, str, bool]) -> None:
        self.results: List[RTFSItem] = results

    def __list__(self):
        return self.results

    def to_embed(self, color: Optional[int] = None):
        description = "\n".join(
            f"[`{result.name}`]({result.url})" for result in self.results
        )

        embed = discord.Embed(description=description, color=color)

        return embed

@dataclass(frozen=True)
class Attribute:
    name: str
    url: str

@dataclass(frozen=True)
class Documentation:
    name: str
    full_name: str
    description: str
    examples: List[str]
    url: str
    fields: Dict[str, List[str]]
    attributes: List[Attribute]

    def to_json(self):
        return {
            v: getattr(self, v)
            for v in dir(self)
            if not v.startswith("_") and v != "to_json"
        }

    def to_embed(self, color: Optional[int] = None):
        description = f"```py\n{self.full_name}\n```\n{self.description}".strip()

        embed = discord.Embed(
            title=self.name, url=self.url, description=description, color=color
        )
        embed.set_author(
            name="discord.py documentation",
            icon_url="https://cdn.discordapp.com/attachments/381963689470984203/1068553303908155442/sW87z7N.png",
        )

        field_limit = 1024
        for name, field in self.fields.items():
            if len(field) > field_limit:
                field = field[: field_limit - 3] + "..."
            embed.add_field(name=name, value=field, inline=False)

        return embed


class SearchResults:
    def __init__(self, results: set[str, str, bool], query_time: int) -> None:
        self.results = results
        self.query_time = query_time

    def __list__(self):
        return self.results

    def to_embed(self, color: Optional[int] = None):
        description = "\n".join(
            f"[`{name}`]({url})" for name, _, url, _ in self.results
        )

        embed = discord.Embed(description=description, color=color)

        query_time = format_timespan(self.query_time)
        embed.set_footer(text=f"Fetched in {query_time}")

        return embed


class DocScraper:
    def __init__(self, browser: Optional[Browser] = None, bot: amyrin = None):
        self._logger: logging.Logger = None

        self._browser = browser
        self._bot = bot

        self._base_url = "https://dpy.rtd.amyr.in/"
        self._inv_url = urljoin(self._base_url, "objects.inv")

        self.strgcls._docs_cache: List[Documentation]
        self.strgcls._docs_caching_progress: Dict[str, Exception]

        self.strgcls._rtfs_commit: Optional[str]
        self.strgcls._rtfs_cache: Optional[
            List[
                TypedDict(
                    "rtfs",
                    {
                        "name": str,
                        "file": str,
                        "position": set[int, int],  # start and end position
                    },
                )
            ]
        ]

        self._rtfs_repo = (
            "discord.py",
            "https://dpy.gh.amyr.in",
            "discord",
        )

        self._setup_logger()
        
        if not getattr(self.strgcls, "_pages", None):
            self.strgcls._pages = {}
        
        if not getattr(self.strgcls, "_docs_caching_progress", None):
            self.strgcls._docs_caching_progress = {}

        if not getattr(self.strgcls, "_docs_cache", None):
            self.strgcls._docs_cache = []

        if not getattr(self.strgcls, "_rtfs_cache", None):
            self.strgcls._rtfs_cache = {}

        if not getattr(self.strgcls, "_inv", None):
            self.strgcls._inv = None

        if not getattr(self.strgcls, "_rtfm_caching_task", None):
            self.strgcls._rtfm_caching_task = asyncio.create_task(
                self._build_rtfm_cache()
            )

        if not getattr(self.strgcls, "_rtfs_caching_task", None):
            self.strgcls._rtfs_caching_task = asyncio.create_task(
                self._build_rtfs_cache()
            )

        if not getattr(self.strgcls, "_docs_caching_task", None):
            self.strgcls._docs_caching_task = asyncio.create_task(
                self._cache_all_documentations()
            )

    @property
    def strgcls(self):
        return self._bot

    def _setup_logger(self) -> None:
        if not os.path.isdir("logs/scrapers"):
            os.mkdir("logs/scrapers")

        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)

        handler = logging.handlers.RotatingFileHandler(
            filename="logs/scrapers/discord_py.log",
            encoding="utf-8",
            maxBytes=32 * 1024 * 1024,  # 32 MiB
            backupCount=5,  # Rotate through 5 files
        )
        dt_fmt = "%Y-%m-%d %H:%M:%S"
        formatter = logging.Formatter(
            "[{asctime}] [{levelname:<8}] {name}: {message}", dt_fmt, style="{"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        self._logger = logger

    async def _shell(self, command: str) -> str:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=60,
        )

        stdout, stderr = await proc.communicate()

        return stdout.decode(), stderr.decode()

    def _rtfs_index_file(self, filepath: os.PathLike) -> None:
        repo, _, _ = self._rtfs_repo

        def append_item(name: str, file: os.PathLike, position: set[int, int]):
            repos_path = os.path.join(os.getcwd(), "rtfs_repos")
            repo_path = os.path.join(repos_path, repo)
            filepath = file[len(repo_path) :]
            path = filepath.split("/")[:-1]

            if "" in path:
                path.remove("")

            name = ".".join(path) + "." + name

            name = name.replace("discord.ext.", "").replace("discord.", "")

            data = {"name": name, "file": filepath, "position": position}
            if not self.strgcls._rtfs_cache:
                self.strgcls._rtfs_cache = []
            self.strgcls._rtfs_cache.append(data)

        with open(filepath) as f:
            code = f.read()

        tree = ast.parse(code)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if node.name.startswith("_"):
                    continue

                class_position = (node.lineno, node.end_lineno)
                append_item(node.name, filepath, class_position)

                for child in node.body:
                    if (
                        not isinstance(child, ast.AsyncFunctionDef)
                        and not isinstance(child, ast.FunctionDef)
                        or child.name.startswith("_")
                    ):
                        continue

                    child_position = (child.lineno, child.end_lineno)

                    name = f"{node.name}.{child.name}"
                    append_item(name, filepath, child_position)

    @executor()
    def _rtfs_index_directory(self, path: os.PathLike):
        for root, _, files in os.walk(path):
            for file in files:
                filepath = os.path.join(root, file)

                if not file.endswith(".py"):
                    continue

                if file.startswith("_"):
                    continue

                self._rtfs_index_file(filepath)

    async def _build_rtfs_cache(self, recache: bool = False, updater: Callable = None):
        if self.strgcls._rtfs_cache != {} and not recache:
            return
        
        if recache:
            self.strgcls._rtfs_cache = {}

        repo, url, dir_name = self._rtfs_repo

        rtfs_repos = os.path.join(os.getcwd(), "rtfs_repos")
        rtfs_repo = os.path.join(rtfs_repos, repo)
        path = os.path.join(rtfs_repo, dir_name)

        if not os.path.isdir(path):
            await self._shell(f"git clone {url} {rtfs_repo}")
            
        commit_path = os.path.join(rtfs_repo, ".git/refs/heads/master")

        with open(commit_path) as f:
            self.strgcls._rtfs_commit = f.readline().strip()

        await self._rtfs_index_directory(path)

        await self.log(updater, "RTFS cache built", "rtfs")

    async def rtfs_search(
        self,
        query: str,
        limit: Optional[int] = None,
        updater: Callable = None,
    ) -> List[RTFSItem]:
        if not self.strgcls._rtfs_caching_task.done():
            await self.update(updater, "Waiting for RTFS caching task")
            await self.strgcls._rtfs_caching_task

        results = []

        _, repo_url, repo_path = self._rtfs_repo

        for item in self.strgcls._rtfs_cache:
            name = item.get("name")
            file = item.get("file")
            start, end = item.get("position")

            file_url = urlparse(repo_url + file)._replace(
                fragment=f"L{start}-L{end}"
            )

            item = RTFSItem(name, file_url.geturl())
            results.append(item)

        matches = sorted(
            results, key=lambda x: fuzz.ratio(query, x.name), reverse=True
        )[:limit]

        return RTFSResults(matches)

    async def _get_html(self, url: str, id: str, timeout: int = 0, wait: bool = True) -> str:
        page = await self._browser.new_page()

        await page.goto(url)

        if wait:
            try:
                await page.wait_for_load_state("networkidle", timeout=timeout)
            except PlaywrightTimeoutError:
                pass

        self.strgcls._pages[id] = page
        return await page.content()

    def _build_url(self, partial_url: str) -> str:
        return self._base_url + partial_url

    def _get_text(
        self, element: Tag, parsed_url: ParseResult, template: str = "[`{}`]({})"
    ):
        if isinstance(element, Tag) and element.name == "a":
            tag_name = element.text
            tag_href = element["href"]

            if parsed_url:
                parsed_href = urlparse(tag_href)
                if not parsed_href.netloc:
                    raw_url = parsed_url._replace(params="", fragment="").geturl()
                    tag_href = urljoin(raw_url, tag_href)

            text = template.format(tag_name, tag_href)
        elif isinstance(element, Tag) and element.name == "strong":
            text = f"**{element.text}**"
        else:
            text = element.text

        return text

    @executor()
    def _get_documentation(self, element: Tag, page_url: str) -> Documentation:
        url = element.find("a", class_="headerlink").get("href", None)
        full_url = urljoin(page_url, url)
        parsed_url = urlparse(full_url)

        parent = element.parent
        
        full_name = element.text
        name = element.attrs.get("id")
        documentation = parent.find("dd")
        description = []
        examples = []
        
        def format_attributes(item: Tag) -> List[Attribute]:
            results: set[str, str] = []
            items = item.find_all("li", class_="py-attribute-table-entry")
            for item in items:
                name = " ".join(x.text for x in item.contents).strip()
                href = item.find("a") \
                    .get("href")
                url = urljoin(full_url, href)
                results.append((name, url))
            
            return results
                    
        attributes: Dict[str, List[Attribute]] = {}
        attribute_list = parent.find("div", class_="py-attribute-table")
        if attribute_list:
            items = attribute_list.findChildren("div", class_="py-attribute-table-column")
            if items:
                attributes["attributes"] = format_attributes(items[0])
                if len(items) >= 2:
                    attributes["methods"] = format_attributes(items[1])

        fields = {}
        
        if supported_operations := documentation.find("div", class_="operations", recursive=False):
            items: List[set[str, str]] = []
            for supported_operation in supported_operations.findChildren("dl", class_="describe"):
                operation = supported_operation \
                    .find("span", class_="descname") \
                    .text.strip()
                desc = self._get_text(
                    supported_operation.find("dd", recursive=False), parsed_url
                ).strip()
                items.append((operation, desc))
                
            if items:
                fields["Supported Operations"] = "\n".join(
                    f"> {operation}\n{desc}"
                    for operation, desc in items
                )
        
        field_list = documentation.find("dl", class_="field-list", recursive=False)
        if field_list:
            for field in field_list.findChildren("dt"):
                field: Tag = field

                key = field.text
                values: List[Tag] = [
                    x for x in field.next_siblings if isinstance(x, Tag)
                ][0].find_all("p")

                elements: List[List[str]] = []
                for value in values:
                    texts = []
                    for element in value.contents:
                        text = self._get_text(
                            element, parsed_url
                        )

                        texts.append(text.replace("\n", " "))

                    elements.append(texts)

                fields[key] = "\n".join("".join(element) for element in elements)

        for child in documentation.find_all("p", recursive=False):
            child: Tag = child

            # this is to stop getting the description after examples,
            # because those are too large, no idea if this will actually works
            if child.attrs.get("class"):
                break

            elements = []
            for element in child.contents:
                text = self._get_text(element, parsed_url)

                elements.append(text)

            description.append("".join(elements))

        for child in documentation.find_all("div", class_=["highlight-python3", "highlight-default"], recursive=False):
            examples.append(child.find("pre").text)

        if version_modified := documentation.find("span", class_="versionmodified"):
            description.append(f"*{version_modified.text}*")

        description = "\n\n".join(description).replace("Example:", "").strip()

        full_name = full_name.replace("¶", "").strip()

        url = parsed_url.geturl()

        return Documentation(
            name=name,
            full_name=full_name,
            description=description,
            examples=examples,
            url=url,
            fields=fields,
            attributes=attributes
        )

    async def _get_all_manual_documentations(self, url: str) -> List[Documentation]:
        @executor()
        def bs4(content: str):
            strainer = SoupStrainer("dl")

            soup = BeautifulSoup(content, "lxml", parse_only=strainer)

            return soup.find_all("dt", class_="sig sig-object py")

        elements = await bs4(await self._get_html(url, url))

        results = []
        for element in elements:
            result = await self._get_documentation(element, url)
            results.append(result)

        return results

    async def log(self, updater: Callable, message: str, name: str):
        await self.update(updater, message, name)
        self._logger.info(message.replace("`", ""))

    async def _cache_all_documentations(
        self, recache: bool = False, updater: Callable = None
    ) -> Dict[str, List[Documentation]]:
        if self.strgcls._docs_cache != [] and not recache:
            return
        
        if recache:
            self.strgcls._docs_cache = []

        await self.log(updater, "Starting documentation caching", "documentation")

        @executor()
        def bs4(content: str) -> List[set[str, str]]:
            soup = BeautifulSoup(content, "lxml")

            manual_section = soup.find("section", id="manuals")
            manual_lis = manual_section.find_all("li", class_="toctree-l1")
            manual_as = [manual_li.find("a") for manual_li in manual_lis]
            return [
                (manual.text, self._build_url(manual.get("href")))
                for manual in manual_as
            ]

        content = await self._get_html(self._base_url, "manuals")
        manuals = await bs4(content)
        
        for name, _ in manuals:
            self.strgcls._docs_caching_progress[name] = None

        results: Dict[str, List[Documentation]] = {}
        for name, manual in manuals:
            try:
                documentations = await self._get_all_manual_documentations(manual)
                
                if name not in results.keys():
                    results[name] = []

                results[name].append(documentations)
                for documentation in documentations:
                    self.strgcls._docs_cache.append(documentation)

                await self.log(
                    updater,
                    f"`{name}` documentation added to documentation cache",
                    "documentation",
                )
            except Exception as exc:
                error = "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                )
                self._logger.error(
                    f'Error occured while trying to cache "{name}":\n{error}'
                )
                self.strgcls._docs_caching_progress[name] = error

        amount = sum(name in results.keys() for name, _ in manuals)
        await self.log(
            updater,
            f"Successfully cached `{amount}`/`{len(manuals)}` manuals",
            "documentation",
        )

        return results

    async def _wait_for_docs(self, name: str, updater: Callable = None):
        while True:
            if self.strgcls._docs_caching_task.cancelled():
                await self.update(updater, f"Documentation caching task has been cancelled, aborting.")
                return False
            elif elem := discord.utils.get(self.strgcls._docs_cache, name=name):
                try:
                    await msg.delete()
                except Exception:
                    pass
                return elem
            elif any(error for _, error in self.strgcls._docs_caching_progress.items()):
                crashed = [name for name, error in self.strgcls._docs_caching_progress.items() if error]
                if len(crashed) == 1:
                    name = crashed[0]
                    await self.update(
                        updater,
                        f"Element could not be found, this could be due to the {name} manual "
                        "caching task having crashed."
                    )
                else:
                    amount = len(crashed)
                    total_amount = len(self.strgcls._docs_caching_progress.keys())
                    await self.update(
                        updater,
                        f"Element could not be found, this could be due to {amount}/{total_amount} manual "
                        "caching tasks having crashed."
                    )
                return False
            elif self.strgcls._docs_caching_task.done():
                await self.update(updater, "Element could not be found")
                return False
            msg = await self.update(updater, f"{LOADING} Waiting for caching task, processing command once it's done.")
            await asyncio.sleep(1)

    async def get_documentation(
        self, name: str, updater: Callable = None
    ) -> Documentation:
        if (
            getattr(self.strgcls, "_docs_cache", None) is None
            and self.strgcls._docs_caching_task.done()
        ):
            await self.update(
                updater,
                f"{LOADING} Documentation cache is not yet built, building now.",
            )
            self.strgcls._docs_caching_task = asyncio.create_task(
                self._cache_all_documentations()
            )

        result = discord.utils.get(self.strgcls._docs_cache, name=name)

        if not result:
            result = await self._wait_for_docs(name, updater)

        if result is False:
            return

        return result

    async def _build_rtfm_cache(self, recache: bool = False, updater: Callable = None):
        if getattr(self.strgcls, "_inv", None) is not None and not recache:
            return
        
        partial = functools.partial(Inventory, url=self._inv_url)
        loop = asyncio.get_running_loop()
        self.strgcls._inv = await loop.run_in_executor(None, partial)

        await self.log(updater, "RTFM cache built", "rtfm")

    async def update(self, updater: Callable, message: str, name: str = None):
        if updater:
            loop = asyncio.get_running_loop()

            args = [message]
            if name and "name" in inspect.signature(updater).parameters.keys():
                args.append(name)

            if inspect.iscoroutinefunction(updater):
                return await updater(*args)

            partial = functools.partial(updater, *args)
            return await loop.run_in_executor(None, partial)

    async def search(
        self,
        query: str,
        limit: int = None,
        exclude_std: bool = False,
        updater: Callable = None,
    ) -> SearchResults:
        if not self.strgcls._rtfm_caching_task.done():
            await self.update(updater, "Waiting for RTFM caching to be done")
            await self.strgcls._rtfm_caching_task
            
        if self.strgcls._rtfm_caching_task.exception() and self.strgcls._inv is None:
            
            
            raise FailedCachingTask(
                "rtfm",
                self.strgcls._rtfm_caching_task.exception(),
                self.strgcls._rtfm_caching_task
            )
                
        with Timer() as timer:
            # implement task error handling later

            def get_name(obj: DataObjStr) -> str:
                name = obj.name if obj.name else obj.dispname if obj.dispname not in ["-", None] else None
                original_name = name

                if obj.domain == "std":
                    name = f"{obj.role}: {name}"

                if self.strgcls._inv.project == "discord.py":
                    name = name.replace("discord.ext.commands.", "").replace(
                        "discord.", ""
                    )

                return name, original_name or name

            def build_uri(obj: DataObjStr) -> str:
                location = obj.uri

                if location.endswith("$"):
                    location = location[:-1] + obj.name

                return urljoin(self._base_url, location)

            matches = sorted(
                self.strgcls._inv.objects,
                key=lambda x: fuzz.ratio(query, x.name),
                reverse=True,
            )

            results = [
                (*get_name(item), build_uri(item), bool(item.domain == "std"))
                for item in matches
            ]

        if exclude_std:
            results = [result for result in results if not result[3]]

        return SearchResults(results=results[:limit], query_time=timer.time)


async def setup(bot):
    pass
