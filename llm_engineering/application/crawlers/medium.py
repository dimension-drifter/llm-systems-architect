from bs4 import BeautifulSoup
from loguru import logger

from llm_engineering.domain.documents import ArticleDocument

from .base import BasePlaywrightCrawler


class MediumCrawler(BasePlaywrightCrawler):
    model = ArticleDocument

    def extract(self, link: str, **kwargs) -> None:
        try:
            old_model = self.model.find(link=link)
            if old_model is not None:
                logger.info(f"Article already exists in the database: {link}")

                return

            logger.info(f"Starting scrapping Medium article: {link}")

            self.page.goto(link)
            self.scroll_page()

            soup = BeautifulSoup(self.page.content(), "html.parser")
            title = soup.find_all("h1", class_="pw-post-title")
            subtitle = soup.find_all("h2", class_="pw-subtitle-paragraph")

            data = {
                "Title": title[0].string if title else None,
                "Subtitle": subtitle[0].string if subtitle else None,
                "Content": soup.get_text(),
            }

            user = kwargs["user"]
            instance = self.model(
                platform="medium",
                content=data,
                link=link,
                author_id=user.id,
                author_full_name=user.full_name,
            )
            instance.save()

            logger.info(f"Successfully scraped and saved article: {link}")
        finally:
            self.close()
