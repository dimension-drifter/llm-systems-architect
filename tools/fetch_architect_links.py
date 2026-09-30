import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests
import yaml
from bs4 import BeautifulSoup
from loguru import logger

LISTING_URLS = {
    "weng": "https://lilianweng.github.io/posts/",
    "huyen": "https://huyenchip.com/blog/",
    "raschka_blog": "https://sebastianraschka.com/blog/",
    "dettmers": "https://timdettmers.com/",
    "willison": "https://simonwillison.net/tags/llms/",
}
_RASCHKA_ARCHIVE_API = "https://magazine.sebastianraschka.com/api/v1/archive"
_AUTHOR_CAP = 100
_RASCHKA_MIN_WORDS = 1000
WILLISON_MIN_WORDS = 800
_WENG_PRE2020_KEEP = {"lm", "attention", "word-embedding"}

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; llm-engineering/0.1)"}
_OUTPUT = Path(__file__).resolve().parent.parent / "configs" / "digital_data_etl_ai_architect.yaml"

_WENG_POST = re.compile(r"^https://lilianweng\.github\.io/posts/\d{4}-\d{2}-\d{2}-[^/]+/?$")
_HUYEN_POST = re.compile(r"^https://huyenchip\.com/\d{4}/\d{2}/\d{2}/[^/]+\.html$")
_RASCHKA_POST = re.compile(r"^https://magazine\.sebastianraschka\.com/p/[A-Za-z0-9-]+$")
_RASCHKA_BLOG_POST = re.compile(r"^https://sebastianraschka\.com/blog/\d{4}/[^/]+\.html$")
_DETTMERS_POST = re.compile(r"^https://timdettmers\.com/\d{4}/\d{2}/\d{2}/[^/]+/?$")
_WILLISON_POST = re.compile(
    r"^https://simonwillison\.net/\d{4}/(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/\d{1,2}/[^/]+/?$"
)
_HF_BLOG = "https://huggingface.co/api/blog"
_HF_CORE_USERS = {"philschmid", "ybelkada", "arthurz", "sgugger", "stas", "timdettmers"}
_HF_CORE_NAMES = {
    "philipp schmid",
    "younes belkada",
    "younes b",
    "arthur zucker",
    "sylvain gugger",
    "stas bekman",
    "tim dettmers",
}
_HF_EXCLUDE = ("audio", "speech", "cv", "robotics", "tabular", "diffusion", "community")
_HF_KEEP_TAGS = {"nlp", "optimization", "research", "rl", "llm", "llms"}
_HF_PINNED = (
    "https://huggingface.co/blog/hf-bitsandbytes-integration",
    "https://huggingface.co/blog/4bit-transformers-bitsandbytes",
    "https://huggingface.co/blog/overview-quantization-transformers",
    "https://huggingface.co/blog/intel-sapphire-rapids",
    "https://huggingface.co/blog/embedding-quantization",
    "https://huggingface.co/blog/pytorch-fsdp",
    "https://huggingface.co/blog/accelerate-deepspeed",
    "https://huggingface.co/blog/starcoder2",
    "https://huggingface.co/blog/optimum-inference",
    "https://huggingface.co/blog/tgi-multi-backend",
    "https://huggingface.co/blog/dpo-trl",
    "https://huggingface.co/blog/pref-tuning",
    "https://huggingface.co/blog/lora",
    "https://huggingface.co/blog/peft",
    "https://huggingface.co/blog/stackllama",
    "https://huggingface.co/blog/llama3",
    "https://huggingface.co/blog/llama31",
    "https://huggingface.co/blog/mixtral",
    "https://huggingface.co/blog/smollm",
)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_HEADERS)
    return session


def _fetch(session: requests.Session, url: str) -> BeautifulSoup:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _clean_url(base: str, href: str) -> str:
    absolute = urljoin(base, href).split("#", 1)[0]
    parsed = urlparse(absolute)
    return urlunparse(parsed._replace(query="", fragment=""))


def _page_number(url: str) -> int:
    match = re.search(r"/page/(\d+)/?", url)
    if match:
        return int(match.group(1))
    match = re.search(r"[?&]page=(\d+)", url)
    if match:
        return int(match.group(1))
    return 1


def _next_numbered_page(soup: BeautifulSoup, current: str, pattern: re.Pattern[str]) -> str | None:
    target = _page_number(current) + 1
    for anchor in soup.find_all("a", href=True):
        href = _clean_url(current, anchor["href"])
        match = pattern.search(href)
        if match and int(match.group(1)) == target:
            return href
    return None


def _walk(session: requests.Session, start: str, next_page) -> list[tuple[str, BeautifulSoup]]:
    pages = []
    seen: set[str] = set()
    url: str | None = start
    while url and url not in seen and len(pages) < 100:
        seen.add(url)
        soup = _fetch(session, url)
        pages.append((url, soup))
        url = next_page(soup, url)
    return pages


def _collect(pages: list[tuple[str, BeautifulSoup]], predicate) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for page_url, soup in pages:
        for anchor in soup.find_all("a", href=True):
            url = _clean_url(page_url, anchor["href"])
            if not predicate(url):
                continue
            key = url.rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            links.append(url)
    return links


def keep_weng_url(url: str) -> bool:
    match = re.search(r"/posts/(\d{4})-\d{2}-\d{2}-([^/]+)/?$", url)
    if match is None:
        return False
    if int(match.group(1)) >= 2020:
        return True
    return match.group(2) in _WENG_PRE2020_KEEP


def keep_willison_post(word_count: int) -> bool:
    return word_count >= WILLISON_MIN_WORDS


def load_author_links(path: Path | None = None) -> list[dict[str, str | list[str]]]:
    config_path = path or _OUTPUT
    parameters = yaml.safe_load(config_path.read_text(encoding="utf-8"))["parameters"]
    return [{"user_full_name": parameters["user_full_name"], "links": list(parameters["links"])}]


def _weng_links(session: requests.Session) -> list[str]:
    pattern = re.compile(r"https://lilianweng\.github\.io/posts/page/(\d+)/?")
    pages = _walk(
        session,
        LISTING_URLS["weng"],
        lambda soup, current: _next_numbered_page(soup, current, pattern),
    )
    return [url for url in _collect(pages, _WENG_POST.match) if keep_weng_url(url)]


def _huyen_links(session: requests.Session) -> list[str]:
    soup = _fetch(session, LISTING_URLS["huyen"])
    return _collect([(LISTING_URLS["huyen"], soup)], _HUYEN_POST.match)


def _parse_time(value: str) -> datetime:
    text = value.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.strptime(text, "%b %d, %Y").replace(tzinfo=timezone.utc)


def _raschka_magazine_links(session: requests.Session) -> list[tuple[datetime, str]]:
    links: list[tuple[datetime, str]] = []
    seen: set[str] = set()
    offset = 0
    while True:
        response = session.get(
            _RASCHKA_ARCHIVE_API,
            params={"sort": "new", "search": "", "offset": offset, "limit": 50},
            timeout=30,
        )
        response.raise_for_status()
        posts = response.json()
        if not posts:
            break
        for post in posts:
            url = (post.get("canonical_url") or "").split("#", 1)[0].split("?", 1)[0]
            wordcount = post.get("wordcount") or 0
            if wordcount < _RASCHKA_MIN_WORDS or not _RASCHKA_POST.match(url) or url in seen:
                continue
            seen.add(url)
            links.append((_parse_time(post.get("post_date") or "Jan 1, 1970"), url))
        # A short page is still a full response. Advance by what came back so the next offset does not skip posts.
        offset += 50 if len(posts) >= 50 else len(posts)
    return links


def _raschka_blog_links(session: requests.Session) -> list[tuple[datetime, str]]:
    soup = _fetch(session, LISTING_URLS["raschka_blog"])
    links: list[tuple[datetime, str]] = []
    seen: set[str] = set()
    for item in soup.select('li[data-blog-type="article"]'):
        anchor = item.find("a", href=True)
        if anchor is None:
            continue
        url = _clean_url(LISTING_URLS["raschka_blog"], anchor["href"])
        if not _RASCHKA_BLOG_POST.match(url) or url in seen:
            continue
        seen.add(url)
        date_node = item.find("span", class_="post-date")
        when = _parse_time(date_node.get_text(strip=True)) if date_node else datetime.min.replace(tzinfo=timezone.utc)
        links.append((when, url))
    return links


def _raschka_links(session: requests.Session) -> list[str]:
    dated = _raschka_magazine_links(session) + _raschka_blog_links(session)
    dated.sort(key=lambda item: item[0], reverse=True)
    links: list[str] = []
    seen: set[str] = set()
    for _, url in dated:
        if url in seen:
            continue
        seen.add(url)
        links.append(url)
        if len(links) >= _AUTHOR_CAP:
            break
    return links


def _dettmers_links(session: requests.Session) -> list[str]:
    pattern = re.compile(r"https://timdettmers\.com/page/(\d+)/?")
    pages = _walk(
        session,
        LISTING_URLS["dettmers"],
        lambda soup, current: _next_numbered_page(soup, current, pattern),
    )
    return _collect(pages, _DETTMERS_POST.match)


def _willison_next(soup: BeautifulSoup, current: str) -> str | None:
    for anchor in soup.find_all("a", href=True):
        if anchor.get_text(strip=True).lower().startswith("next"):
            return urljoin(current, anchor["href"])
    return None


def _willison_links(session: requests.Session) -> list[str]:
    links: list[str] = []
    seen_urls: set[str] = set()
    seen_pages: set[str] = set()
    url: str | None = LISTING_URLS["willison"]
    while url and url not in seen_pages and len(links) < _AUTHOR_CAP:
        seen_pages.add(url)
        soup = _fetch(session, url)
        for entry in soup.select('div[data-type="entry"]'):
            anchor = entry.select_one("a[rel=bookmark]")
            if anchor is None:
                continue
            post_url = _clean_url(url, anchor["href"])
            key = post_url.rstrip("/")
            if not _WILLISON_POST.match(post_url) or key in seen_urls:
                continue
            seen_urls.add(key)
            word_count = _entry_word_count(session, post_url)
            if word_count is not None and not keep_willison_post(word_count):
                logger.info(f"Skipping short Willison post ({word_count} words): {post_url}")
                continue
            links.append(post_url)
            if len(links) >= _AUTHOR_CAP:
                break
        url = _willison_next(soup, url)
    return links


def _hf_author_ok(authors: list[dict]) -> bool:
    for author in authors:
        if author.get("isHf"):
            return True
        if (author.get("name") or "").casefold() in _HF_CORE_USERS:
            return True
        if (author.get("fullname") or "").casefold() in _HF_CORE_NAMES:
            return True
    return False


def _hf_tags_ok(tags: list[str]) -> bool:
    lowered = [tag.casefold() for tag in tags]
    if any(any(blocked in tag for blocked in _HF_EXCLUDE) for tag in lowered):
        return False
    return any(tag in _HF_KEEP_TAGS for tag in lowered)


def _huggingface_links(session: requests.Session) -> list[str]:
    links = list(_HF_PINNED)
    seen = {url.rstrip("/") for url in links}
    page = 0
    while page < 80:
        response = session.get(_HF_BLOG, params={"p": page}, timeout=30)
        response.raise_for_status()
        blogs = response.json().get("allBlogs") or []
        if not blogs:
            break
        for blog in blogs:
            published = blog.get("publishedAt") or ""
            year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else 0
            if year < 2020 or year > 2026:
                continue
            if not _hf_author_ok(blog.get("authorsData") or []):
                continue
            if not _hf_tags_ok(blog.get("tags") or []):
                continue
            raw_url = blog.get("url") or ""
            if raw_url.startswith("/"):
                raw_url = "https://huggingface.co" + raw_url
            url = raw_url.split("?", 1)[0].rstrip("/")
            if not url.startswith("https://huggingface.co/blog/") or url in seen:
                continue
            seen.add(url)
            links.append(url)
        page += 1
    return links


def _entry_word_count(session: requests.Session, url: str) -> int | None:
    try:
        soup = _fetch(session, url)
    except requests.RequestException:
        logger.exception(f"Could not measure Willison post, keeping it: {url}")
        return None
    node = soup.select_one("div.entry")
    if node is None:
        logger.warning(f"No Willison entry node, keeping it: {url}")
        return None
    return len(node.get_text(" ", strip=True).split())


def _saved_huggingface_links(path: Path) -> list[str]:
    if not path.exists():
        return []
    parameters = yaml.safe_load(path.read_text(encoding="utf-8")).get("parameters", {})
    return [url for url in parameters.get("links", []) if urlparse(url).netloc == "huggingface.co"]


def prune_corpus_file(path: Path | None = None) -> None:
    config_path = path or _OUTPUT
    document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    links = list(document["parameters"]["links"])
    session = _session()
    kept: list[str] = []
    for url in links:
        host = urlparse(url).netloc
        if host == "lilianweng.github.io":
            if keep_weng_url(url):
                kept.append(url)
            else:
                logger.info(f"Dropping off-topic Weng post: {url}")
            continue
        if host == "simonwillison.net":
            word_count = _entry_word_count(session, url)
            if word_count is not None and not keep_willison_post(word_count):
                logger.info(f"Dropping short Willison post ({word_count} words): {url}")
                continue
        kept.append(url)
    document["parameters"]["links"] = kept
    config_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=1000),
        encoding="utf-8",
    )
    logger.info(f"Pruned {len(links) - len(kept)} links. {len(kept)} remain in {config_path}")


def main() -> None:
    session = _session()
    grouped = {
        "weng": _weng_links(session),
        "huyen": _huyen_links(session),
        "raschka": _raschka_links(session),
        "dettmers": _dettmers_links(session),
        "willison": _willison_links(session),
        "huggingface": _huggingface_links(session),
    }
    for author, author_links in grouped.items():
        logger.info(f"{author}: {len(author_links)} links")
    links = [url for author_links in grouped.values() for url in author_links]
    seen = {url.rstrip("/") for url in links}
    for url in _saved_huggingface_links(_OUTPUT):
        if url.rstrip("/") not in seen:
            links.append(url)
            seen.add(url.rstrip("/"))
    document = {
        "parameters": {
            "user_full_name": "Staff AI Architect",
            "links": links,
        }
    }
    _OUTPUT.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=1000),
        encoding="utf-8",
    )
    logger.info(f"Wrote {len(links)} links to {_OUTPUT}")


if __name__ == "__main__":
    main()
