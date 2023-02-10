import inspect
import re
from dataclasses import dataclass
from typing import List
from urllib.parse import quote_plus

from bs4 import BeautifulSoup, Tag
from playwright.async_api._generated import Browser


class Response:
    def __bool__(self):
        return any(
            getattr(self, str(attr)) for attr in dir(self) if not attr.startswith("_")
        )

    def to_json(self):
        result = {}
        for attr in dir(self):
            if attr.startswith("_") or attr == "to_json":
                continue

            val = getattr(self, attr)
            if hasattr(val, "to_json"):
                func = getattr(val, "to_json")
                if inspect.iscoroutinefunction(func):
                    continue

                result[attr] = func()
            else:
                result[attr] = val

        return result


class VerificationError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "MusixMatch has responded with human verification, and there is no bypasser, atleast yet."
        )


@dataclass(unsafe_hash=True, frozen=True)
class Artist(Response):
    name: str
    url: str


@dataclass(unsafe_hash=True, frozen=True)
class SearchResult(Response):
    title: str
    artist: Artist
    url: str
    album_cover: str


@dataclass(unsafe_hash=True, frozen=True)
class Song(Response):
    title: str
    artist: Artist
    url: str
    lyrics: str
    album_cover: str


class SearchResults(list):
    def __init_subclass__(cls) -> List[SearchResult]:
        return super().__init_subclass__()

    def to_json(self):
        return [x.to_json() for x in self]


class MusixMatchScraper:
    def __init__(self, browser: Browser = None):
        self._browser = browser

        self._base_url = "https://www.musixmatch.com"
        self._search_album_cover_regex = r"https:\/\/s\.mxmcdn\.net\/images-storage\/albums\d?\/\d\/\d\/\d\/\d\/\d\/\d\/[\d_]+\.jpg"

    async def _get_search_soup(self, query: str) -> BeautifulSoup:
        formatted_query = quote_plus(query)

        url = self._build_url(f"/search/{formatted_query}/tracks")

        return await self._get_soup(url)

    async def _get_soup(self, url: str) -> BeautifulSoup:
        page = await self._browser.new_page()

        await page.goto(url)

        human_verification = page.locator(".mxm-human-verify")
        if await human_verification.is_visible():
            raise VerificationError()

        content = await page.content()
        await page.close()

        return BeautifulSoup(content, "html.parser")

    def _build_url(self, partial_url: str) -> str:
        return self._base_url + partial_url

    async def search(self, query: str, lyrics_only: bool = False) -> SearchResults:
        soup = await self._get_search_soup(query)

        tracks_elem: Tag = soup.find("ul", class_="tracks")
        tracks: List[Tag] = tracks_elem.find_all("li")

        results = SearchResults()
        for track in tracks:
            add_lyrics_button = track.find("a", class_="add-lyrics-button")
            if add_lyrics_button is not None and lyrics_only:
                continue

            title_tag = track.find("h2", "media-card-title").find("a", class_="title")
            title = title_tag.find("span").text
            title_url = title_tag.get("href")
            url = self._build_url(title_url)

            artist_container = track.find("h3", class_="media-card-subtitle").find("a")
            artist_url = self._build_url(artist_container["href"])
            artist_name = artist_container.text
            artist = Artist(artist_name, artist_url)

            album_cover = (
                track.find("div", "media-card-picture").find("img").get("srcset")
            )
            album_cover_variations = re.findall(
                self._search_album_cover_regex, album_cover
            )
            best_album_cover = (
                album_cover_variations[-1] if album_cover_variations else None
            )

            results.append(SearchResult(title, artist, url, best_album_cover))

        return results

    async def get_song(self, url: str) -> Song:
        soup = await self._get_soup(url)

        lyrics_container = soup.find("div", class_="mxm-lyrics")

        lyric_containers = lyrics_container.find("span").children
        lyrics = "\n".join(i.text for i in lyric_containers).strip()

        if lyrics == "":
            lyrics = "Failed to load lyrics."

        info_container = soup.find("div", class_="mxm-track-title")

        title = "".join(
            list(info_container.find("h1", class_="mxm-track-title__track"))[1:]
        )

        artist_container = info_container.find("h2").find("a")
        artist_url = self._build_url(artist_container["href"])
        artist_name = artist_container.text
        artist = Artist(artist_name, artist_url)

        album_cover = (
            soup.find("div", class_="banner-album-image-desktop").find("img").get("src")
        )

        if album_cover.startswith("//"):
            album_cover = "https:" + album_cover

        return Song(title, artist, url, lyrics, album_cover)


async def setup(bot):
    pass
