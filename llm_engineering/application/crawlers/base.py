import time
from abc import ABC, abstractmethod

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from llm_engineering.domain.documents import NoSQLBaseDocument


class BaseCrawler(ABC):
    model: type[NoSQLBaseDocument]

    @abstractmethod
    def extract(self, link: str, **kwargs) -> None: ...


class BasePlaywrightCrawler(BaseCrawler, ABC):
    def __init__(self, scroll_limit: int = 5) -> None:
        self.scroll_limit = scroll_limit
        self._closed = False
        self._playwright: Playwright = sync_playwright().start()
        try:
            self._browser: Browser = self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-popup-blocking",
                    "--disable-notifications",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--ignore-certificate-errors",
                ],
            )
            self.page: Page = self._browser.new_page()
            self.page.set_default_navigation_timeout(300_000)
        except Exception:
            self._playwright.stop()
            self._closed = True
            raise

    def login(self) -> None:
        pass

    def scroll_page(self) -> None:
        """Scroll through the LinkedIn page based on the scroll limit."""
        current_scroll = 0
        last_height = self.page.evaluate("document.body.scrollHeight")
        while True:
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(5)
            new_height = self.page.evaluate("document.body.scrollHeight")
            if new_height == last_height or (self.scroll_limit and current_scroll >= self.scroll_limit):
                break
            last_height = new_height
            current_scroll += 1

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.page.close()
        finally:
            try:
                self._browser.close()
            finally:
                self._playwright.stop()
