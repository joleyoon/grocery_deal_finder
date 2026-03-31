from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock

from flask import Flask
from sqlalchemy.orm import Session

from grocery_scraper.driver import build_chrome_driver
from grocery_scraper.models import ProductPrice
from grocery_scraper.stores import ScraperSettings, build_scrapers

from ..db import get_session_factory
from ..models import utcnow
from .catalog import STORE_NAMES, search_listings, upsert_scraped_result

REFRESH_STATUS_RETENTION = timedelta(minutes=15)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def target_store_slugs(store_slug: str | None) -> list[str]:
    if store_slug:
        if store_slug not in STORE_NAMES:
            return []
        return [store_slug]
    return list(STORE_NAMES)


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

    target_stores = target_store_slugs(store_slug)
    if not target_stores:
        return []

    rows = search_listings(
        session,
        query=cleaned_query,
        store_slug=store_slug,
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


def refresh_query(
    session: Session,
    *,
    query: str,
    store_slug: str | None,
    limit: int,
    stores: list[str] | None = None,
    zip_code: str | None = None,
    wholefoods_store: str | None = None,
    chrome_binary: str | None = None,
    show_browser: bool = False,
    timeout: int = 20,
    pause_seconds: float = 1.0,
) -> list[str]:
    cleaned_query = query.strip()
    target_stores = list(dict.fromkeys(stores or target_store_slugs(store_slug)))
    if not cleaned_query or not target_stores:
        return []

    results = collect_prices(
        keyword=cleaned_query,
        stores=target_stores,
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
    return target_stores


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


def refresh_job_key(query: str, stores: list[str], limit: int) -> str:
    normalized_stores = ",".join(sorted(stores))
    return f"{query.strip().lower()}::{normalized_stores}::{max(1, min(limit, 25))}"


def _refresh_executor(app: Flask) -> ThreadPoolExecutor:
    executor = app.extensions.get("collector_refresh_executor")
    if executor is None:
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="catalog-refresh")
        app.extensions["collector_refresh_executor"] = executor
    return executor


def _refresh_lock(app: Flask) -> Lock:
    lock = app.extensions.get("collector_refresh_lock")
    if lock is None:
        lock = Lock()
        app.extensions["collector_refresh_lock"] = lock
    return lock


def _refresh_statuses(app: Flask) -> dict[str, dict[str, object]]:
    statuses = app.extensions.get("collector_refresh_statuses")
    if statuses is None:
        statuses = {}
        app.extensions["collector_refresh_statuses"] = statuses
    return statuses


def _inflight_refreshes(app: Flask) -> set[str]:
    inflight = app.extensions.get("collector_inflight_refreshes")
    if inflight is None:
        inflight = set()
        app.extensions["collector_inflight_refreshes"] = inflight
    return inflight


def _serialize_refresh_status(status: dict[str, object] | None) -> dict[str, object] | None:
    if status is None:
        return None
    return {
        "key": status["key"],
        "query": status["query"],
        "stores": list(status["stores"]),
        "limit": status["limit"],
        "state": status["state"],
        "error": status["error"],
        "created_at": status["created_at"].isoformat(),
        "started_at": status["started_at"].isoformat() if status["started_at"] else None,
        "finished_at": status["finished_at"].isoformat() if status["finished_at"] else None,
        "updated_at": status["updated_at"].isoformat(),
    }


def _prune_refresh_statuses(app: Flask) -> None:
    cutoff = utcnow() - REFRESH_STATUS_RETENTION
    statuses = _refresh_statuses(app)
    inflight = _inflight_refreshes(app)
    for key, status in list(statuses.items()):
        if key in inflight:
            continue
        reference_time = status.get("finished_at") or status.get("updated_at") or status.get("created_at")
        if isinstance(reference_time, datetime) and _as_utc(reference_time) < cutoff:
            del statuses[key]


def get_refresh_status(app: Flask, refresh_key: str) -> dict[str, object] | None:
    with _refresh_lock(app):
        _prune_refresh_statuses(app)
        return _serialize_refresh_status(_refresh_statuses(app).get(refresh_key))


def _set_refresh_status(
    app: Flask,
    refresh_key: str,
    *,
    query: str,
    stores: list[str],
    limit: int,
    state: str,
) -> None:
    now = utcnow()
    _refresh_statuses(app)[refresh_key] = {
        "key": refresh_key,
        "query": query,
        "stores": tuple(stores),
        "limit": max(1, min(limit, 25)),
        "state": state,
        "error": None,
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "updated_at": now,
    }


def _update_refresh_status(app: Flask, refresh_key: str, **updates: object) -> None:
    status = _refresh_statuses(app).get(refresh_key)
    if status is None:
        return
    status.update(updates)
    status["updated_at"] = utcnow()


def _run_scheduled_refresh(
    app: Flask,
    *,
    refresh_key: str,
    query: str,
    store_slug: str | None,
    stores: list[str],
    limit: int,
    zip_code: str | None,
    wholefoods_store: str | None,
    chrome_binary: str | None,
    show_browser: bool,
    timeout: int,
    pause_seconds: float,
) -> None:
    session_factory = get_session_factory(app)
    session = session_factory()
    try:
        with _refresh_lock(app):
            _update_refresh_status(
                app,
                refresh_key,
                state="running",
                started_at=utcnow(),
                error=None,
                finished_at=None,
            )
        refresh_query(
            session,
            query=query,
            store_slug=store_slug,
            limit=limit,
            stores=stores,
            zip_code=zip_code,
            wholefoods_store=wholefoods_store,
            chrome_binary=chrome_binary,
            show_browser=show_browser,
            timeout=timeout,
            pause_seconds=pause_seconds,
        )
        with _refresh_lock(app):
            _update_refresh_status(
                app,
                refresh_key,
                state="completed",
                error=None,
                finished_at=utcnow(),
            )
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        with _refresh_lock(app):
            _update_refresh_status(
                app,
                refresh_key,
                state="failed",
                error=str(exc),
                finished_at=utcnow(),
            )
        app.logger.exception(
            "Background catalog refresh failed for query=%s stores=%s",
            query,
            ",".join(stores),
        )
    finally:
        session.close()
        session_factory.remove()
        with _refresh_lock(app):
            _inflight_refreshes(app).discard(refresh_key)


def schedule_query_refresh(
    app: Flask,
    *,
    query: str,
    store_slug: str | None,
    limit: int,
    stores: list[str] | None = None,
    zip_code: str | None = None,
    wholefoods_store: str | None = None,
    chrome_binary: str | None = None,
    show_browser: bool = False,
    timeout: int = 20,
    pause_seconds: float = 1.0,
) -> list[str]:
    cleaned_query = query.strip()
    target_stores = list(dict.fromkeys(stores or target_store_slugs(store_slug)))
    if not cleaned_query or not target_stores:
        return []

    refresh_key = refresh_job_key(cleaned_query, target_stores, limit)
    with _refresh_lock(app):
        _prune_refresh_statuses(app)
        inflight = _inflight_refreshes(app)
        if refresh_key in inflight:
            return target_stores
        inflight.add(refresh_key)
        _set_refresh_status(
            app,
            refresh_key,
            query=cleaned_query,
            stores=target_stores,
            limit=limit,
            state="queued",
        )

    _refresh_executor(app).submit(
        _run_scheduled_refresh,
        app,
        refresh_key=refresh_key,
        query=cleaned_query,
        store_slug=store_slug,
        stores=target_stores,
        limit=limit,
        zip_code=zip_code,
        wholefoods_store=wholefoods_store,
        chrome_binary=chrome_binary,
        show_browser=show_browser,
        timeout=timeout,
        pause_seconds=pause_seconds,
    )
    return target_stores


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

    return refresh_query(
        session,
        query=query,
        store_slug=store_slug,
        limit=limit,
        stores=stale_stores,
        zip_code=zip_code,
        wholefoods_store=wholefoods_store,
        chrome_binary=chrome_binary,
        show_browser=show_browser,
        timeout=timeout,
        pause_seconds=pause_seconds,
    )
