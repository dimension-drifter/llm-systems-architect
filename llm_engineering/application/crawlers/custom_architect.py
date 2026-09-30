import time
from urllib.parse import urlparse

import html2text
import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
from loguru import logger

from llm_engineering.domain.documents import ArticleDocument

from .base import BaseCrawler

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; llm-engineering/0.1)"}


class _ArchitectCrawler(BaseCrawler):
    model = ArticleDocument
    selectors: tuple[str, ...] = ()
    default_author: str = ""
    force_author: bool = False

    def extract(self, link: str, **kwargs) -> None:
        old_model = self.model.find(link=link)
        if old_model is not None:
            logger.info(f"Article already exists in the database: {link}")

            return

        logger.info(f"Starting scrapping article: {link}")

        soup = BeautifulSoup(_fetch_html(link), "html.parser")
        node = _select_content(soup, self.selectors)
        if node is None:
            raise ValueError(f"No article content found for {link}")

        parsed_url = urlparse(link)
        user = kwargs["user"]
        author_name = self.default_author if self.force_author else (_extract_author(soup) or self.default_author)
        instance = self.model(
            content={
                "Title": _extract_title(soup),
                "Author": author_name,
                "URL": link,
                "Content": _html_to_text(self.prepare_node(node)),
            },
            link=link,
            platform=parsed_url.netloc,
            author_id=user.id,
            author_full_name=author_name if self.force_author else user.full_name,
        )
        instance.save()

        logger.info(f"Finished scrapping article: {link}")

    def prepare_node(self, node: Tag) -> Tag:
        return node


class WengCrawler(_ArchitectCrawler):
    # Live posts use div.post-content. The first two selectors are the requested names.
    selectors = ("article.post-content", ".post", "div.post-content")
    default_author = "Lilian Weng"


class HuyenCrawler(_ArchitectCrawler):
    selectors = ("div.entry-content", "article")
    default_author = "Chip Huyen"


class RaschkaCrawler(_ArchitectCrawler):
    selectors = ("div.available-content", ".post-content")
    default_author = "Sebastian Raschka"


class DettmersCrawler(_ArchitectCrawler):
    selectors = ("div.entry-content",)
    default_author = "Tim Dettmers"


class WillisonCrawler(_ArchitectCrawler):
    selectors = ("div.entry",)
    default_author = "Simon Willison"


class HuggingFaceCrawler(_ArchitectCrawler):
    selectors = ("div.blog-content", "div.prose")
    default_author = "Hugging Face"
    force_author = True

    def prepare_node(self, node: Tag) -> Tag:
        for block in node.select("div.not-prose"):
            if block.select_one(".fullname"):
                block.decompose()

        return node


def _fetch_html(url: str) -> str:
    delay = 2.0
    response: requests.Response | None = None
    for _ in range(6):
        response = requests.get(url, headers=_HEADERS, timeout=30)
        if response.status_code not in {429, 503}:
            response.raise_for_status()
            return response.text
        retry_after = response.headers.get("Retry-After")
        wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
        logger.warning(f"Retrying {url} in {wait:.0f}s after HTTP {response.status_code}")
        time.sleep(wait)
        delay = min(delay * 2, 60)
    assert response is not None
    response.raise_for_status()
    return response.text


def _select_content(soup: BeautifulSoup, selectors: tuple[str, ...]) -> Tag | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if node is not None:
            return node
    return None


def _extract_title(soup: BeautifulSoup) -> str | None:
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()

    for selector in ("h1.post-title", "h1.entry-title", "h1"):
        node = soup.select_one(selector)
        if node is None:
            continue
        text = node.get_text(" ", strip=True)
        if text:
            return text
    return None


def _extract_author(soup: BeautifulSoup) -> str | None:
    for attrs in ({"name": "author"}, {"property": "author"}, {"property": "article:author"}):
        node = soup.find("meta", attrs=attrs)
        if node and node.get("content"):
            return node["content"].strip()
    return None


_CHROME_SELECTORS = (
    "nav",
    "footer",
    "aside",
    "script",
    "style",
    "noscript",
    "iframe",
    "form",
    ".share",
    ".cite-share",
    "[class*='cite-share']",
    ".sharedaddy",
    ".newsletter",
    ".subscribe",
    ".social-share",
    ".entry-footer",
    ".jp-relatedposts",
)


def _strip_chrome(node: Tag) -> None:
    for selector in _CHROME_SELECTORS:
        for match in node.select(selector):
            match.decompose()


def _html_to_text(node: Tag) -> str:
    _strip_chrome(node)
    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.protect_links = True
    converter.unicode_snob = True
    return converter.handle(str(node)).strip()
