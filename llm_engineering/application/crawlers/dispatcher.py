import re
from urllib.parse import urlparse

from loguru import logger

from .base import BaseCrawler
from .custom_architect import (
    DettmersCrawler,
    HuggingFaceCrawler,
    HuyenCrawler,
    RaschkaCrawler,
    WengCrawler,
    WillisonCrawler,
)
from .custom_article import CustomArticleCrawler
from .github import GithubCrawler
from .linkedin import LinkedInCrawler
from .medium import MediumCrawler


class CrawlerDispatcher:
    def __init__(self) -> None:
        self._crawlers = {}

    @classmethod
    def build(cls) -> "CrawlerDispatcher":
        dispatcher = cls()

        return dispatcher

    def register_medium(self) -> "CrawlerDispatcher":
        self.register("https://medium.com", MediumCrawler)

        return self

    def register_linkedin(self) -> "CrawlerDispatcher":
        self.register("https://linkedin.com", LinkedInCrawler)

        return self

    def register_github(self) -> "CrawlerDispatcher":
        self.register("https://github.com", GithubCrawler)

        return self

    def register_weng(self) -> "CrawlerDispatcher":
        self.register("https://lilianweng.github.io", WengCrawler)

        return self

    def register_huyen(self) -> "CrawlerDispatcher":
        self.register("https://huyenchip.com", HuyenCrawler)

        return self

    def register_raschka(self) -> "CrawlerDispatcher":
        self.register("https://magazine.sebastianraschka.com", RaschkaCrawler)
        self.register("https://sebastianraschka.com", RaschkaCrawler)

        return self

    def register_dettmers(self) -> "CrawlerDispatcher":
        self.register("https://timdettmers.com", DettmersCrawler)

        return self

    def register_willison(self) -> "CrawlerDispatcher":
        self.register("https://simonwillison.net", WillisonCrawler)

        return self

    def register_huggingface(self) -> "CrawlerDispatcher":
        self.register("https://huggingface.co", HuggingFaceCrawler)

        return self

    def register(self, domain: str, crawler: type[BaseCrawler]) -> None:
        parsed_domain = urlparse(domain)
        domain = parsed_domain.netloc

        self._crawlers[r"https://(www\.)?{}/*".format(re.escape(domain))] = crawler

    def get_crawler(self, url: str) -> BaseCrawler:
        for pattern, crawler in self._crawlers.items():
            if re.match(pattern, url):
                return crawler()
        else:
            logger.warning(f"No crawler found for {url}. Defaulting to CustomArticleCrawler.")

            return CustomArticleCrawler()


def build_crawler_dispatcher() -> CrawlerDispatcher:
    return (
        CrawlerDispatcher.build()
        .register_linkedin()
        .register_medium()
        .register_github()
        .register_weng()
        .register_huyen()
        .register_raschka()
        .register_dettmers()
        .register_willison()
        .register_huggingface()
    )
