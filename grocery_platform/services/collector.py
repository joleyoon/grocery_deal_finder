from __future__ import annotations

from grocery_scraper.driver import build_chrome_driver
from grocery_scraper.models import ProductPrice
from grocery_scraper.stores import ScraperSettings, build_scrapers


def collect_prices(
    *,
    keyword: str,
    stores: list[str],
    limit: int,
    zip_code: str | None,
    wholefoods_store: str | None,
    chrome_binary: str | None,
    show_browser: bool,
    timeout: int,
    pause_seconds: float,
) -> list[ProductPrice]:
    settings = ScraperSettings(
        limit=limit,
        timeout=timeout,
        pause_seconds=pause_seconds,
    )
    driver = build_chrome_driver(
        headless=not show_browser,
        page_load_timeout=timeout,
        chrome_binary=chrome_binary,
    )
    try:
        scrapers = build_scrapers(
            driver,
            settings,
            zip_code=zip_code,
            wholefoods_store=wholefoods_store,
        )
        results: list[ProductPrice] = []
        for store in stores:
            results.extend(scrapers[store].scrape(keyword))
        return results
    finally:
        driver.quit()
