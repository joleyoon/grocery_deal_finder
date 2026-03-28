from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from grocery_scraper.driver import build_chrome_driver
from grocery_scraper.models import ProductPrice
from grocery_scraper.stores import ScraperSettings, build_scrapers

from ..models import utcnow
from .catalog import STORE_NAMES, search_listings, upsert_scraped_result


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def stale_store_slugs(
    session: Session,
    *,
    query: str,
    store_slug: str | None,
    stale_after_hours: int,
    search_limit: int,
) -> list[str]:
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    if store_slug:
        if store_slug not in STORE_NAMES:
            return []
        target_stores = [store_slug]
    else:
        target_stores = list(STORE_NAMES)

    rows = search_listings(
        session,
        query=cleaned_query,
        store_slug=store_slug,
        in_stock_only=False,
        limit=max(search_limit, 100),
    )
    cutoff = utcnow() - timedelta(hours=stale_after_hours)

    stale_stores: list[str] = []
    for slug in target_stores:
        store_rows = [row for row in rows if row.store.slug == slug]
        if not store_rows:
            stale_stores.append(slug)
            continue
        freshest_seen = max(_as_utc(row.last_seen_at) for row in store_rows)
        if freshest_seen <= cutoff:
            stale_stores.append(slug)
    return stale_stores


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


def refresh_query_if_stale(
    session: Session,
    *,
    query: str,
    store_slug: str | None,
    limit: int,
    stale_after_hours: int,
    zip_code: str | None = None,
    wholefoods_store: str | None = None,
    chrome_binary: str | None = None,
    show_browser: bool = False,
    timeout: int = 20,
    pause_seconds: float = 1.0,
) -> list[str]:
    stale_stores = stale_store_slugs(
        session,
        query=query,
        store_slug=store_slug,
        stale_after_hours=stale_after_hours,
        search_limit=limit,
    )
    if not stale_stores:
        return []

    results = collect_prices(
        keyword=query,
        stores=stale_stores,
        limit=max(1, min(limit, 25)),
        zip_code=zip_code,
        wholefoods_store=wholefoods_store,
        chrome_binary=chrome_binary,
        show_browser=show_browser,
        timeout=timeout,
        pause_seconds=pause_seconds,
    )
    for result in results:
        if not result.title and not result.price_text and result.note:
            continue
        upsert_scraped_result(session, result)
    session.commit()
    return stale_stores
