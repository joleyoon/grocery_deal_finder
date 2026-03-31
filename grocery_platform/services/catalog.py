from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from flask import Flask
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, joinedload

from grocery_scraper.models import ProductPrice

from ..models import Listing, PriceHistory, Store, utcnow


STORE_NAMES = {
    "target": "Target",
    "wholefoods": "Whole Foods",
    "traderjoes": "Trader Joe's",
}


def normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def ensure_store(session: Session, slug: str) -> Store:
    store = session.scalar(select(Store).where(Store.slug == slug))
    if store:
        return store
    store = Store(slug=slug, name=STORE_NAMES.get(slug, slug.title()))
    session.add(store)
    session.flush()
    return store


def seed_stores(session: Session) -> list[Store]:
    stores = [ensure_store(session, slug) for slug in STORE_NAMES]
    session.flush()
    return stores


def listing_query() -> Select[tuple[Listing]]:
    return select(Listing).options(joinedload(Listing.store))


@dataclass
class ListingSearchResult:
    items: list[Listing]
    refreshed_stores: list[str] = field(default_factory=list)
    refresh_error: str | None = None
    refresh_mode: str = "none"
    refresh_status: dict[str, object] | None = None
    stale_after_hours: int = 24

    @property
    def refreshed(self) -> bool:
        return self.refresh_mode != "none"


def search_listings(
    session: Session,
    *,
    query: str | None,
    store_slug: str | None,
    limit: int,
) -> list[Listing]:
    stmt = listing_query().order_by(Listing.updated_at.desc(), Listing.title.asc())
    if store_slug:
        stmt = stmt.join(Listing.store).where(Store.slug == store_slug)
    if query:
        pattern = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                Listing.title.ilike(pattern),
                Listing.keyword.ilike(pattern),
                Listing.normalized_title.ilike(pattern.lower()),
            )
        )
    return list(session.scalars(stmt.limit(limit)))


def search_listings_cached(
    session: Session,
    *,
    query: str | None,
    store_slug: str | None,
    limit: int,
    stale_after_hours: int,
    refresh_if_stale: bool = False,
    force_refresh: bool = False,
    app: Flask | None = None,
    background_refresh: bool = True,
    zip_code: str | None = None,
    wholefoods_store: str | None = None,
    chrome_binary: str | None = None,
    show_browser: bool = False,
    timeout: int = 20,
    pause_seconds: float = 1.0,
) -> ListingSearchResult:
    rows = search_listings(
        session,
        query=query,
        store_slug=store_slug,
        limit=limit,
    )
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        return ListingSearchResult(items=rows, stale_after_hours=stale_after_hours)

    from .collector import (
        get_refresh_status,
        refresh_job_key,
        refresh_query,
        schedule_query_refresh,
        stale_store_slugs,
        target_store_slugs,
    )

    try:
        if not rows:
            refreshed_stores = refresh_query(
                session,
                query=cleaned_query,
                store_slug=store_slug,
                limit=limit,
                zip_code=zip_code,
                wholefoods_store=wholefoods_store,
                chrome_binary=chrome_binary,
                show_browser=show_browser,
                timeout=timeout,
                pause_seconds=pause_seconds,
            )
            return ListingSearchResult(
                items=search_listings(
                    session,
                    query=query,
                    store_slug=store_slug,
                    limit=limit,
                ),
                refreshed_stores=refreshed_stores,
                refresh_mode="blocking" if refreshed_stores else "none",
                stale_after_hours=stale_after_hours,
            )

        stores_to_refresh: list[str] = []
        if force_refresh:
            stores_to_refresh = target_store_slugs(store_slug)
        elif refresh_if_stale:
            stores_to_refresh = stale_store_slugs(
                session,
                query=cleaned_query,
                store_slug=store_slug,
                stale_after_hours=stale_after_hours,
                search_limit=limit,
            )

        if not stores_to_refresh:
            return ListingSearchResult(items=rows, stale_after_hours=stale_after_hours)

        if app is not None and background_refresh:
            refreshed_stores = schedule_query_refresh(
                app,
                query=cleaned_query,
                store_slug=store_slug,
                limit=limit,
                stores=stores_to_refresh,
                zip_code=zip_code,
                wholefoods_store=wholefoods_store,
                chrome_binary=chrome_binary,
                show_browser=show_browser,
                timeout=timeout,
                pause_seconds=pause_seconds,
            )
            refresh_status = None
            if refreshed_stores:
                refresh_status = get_refresh_status(
                    app,
                    refresh_job_key(cleaned_query, refreshed_stores, limit),
                )
            return ListingSearchResult(
                items=rows,
                refreshed_stores=refreshed_stores,
                refresh_mode="background" if refreshed_stores else "none",
                refresh_status=refresh_status,
                stale_after_hours=stale_after_hours,
            )

        refreshed_stores = refresh_query(
            session,
            query=cleaned_query,
            store_slug=store_slug,
            limit=limit,
            stores=stores_to_refresh,
            zip_code=zip_code,
            wholefoods_store=wholefoods_store,
            chrome_binary=chrome_binary,
            show_browser=show_browser,
            timeout=timeout,
            pause_seconds=pause_seconds,
        )
        return ListingSearchResult(
            items=search_listings(
                session,
                query=query,
                store_slug=store_slug,
                limit=limit,
            ),
            refreshed_stores=refreshed_stores,
            refresh_mode="blocking" if refreshed_stores else "none",
            stale_after_hours=stale_after_hours,
        )
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        return ListingSearchResult(
            items=rows,
            refresh_error=str(exc),
            stale_after_hours=stale_after_hours,
        )


def get_listing_or_404(session: Session, listing_id: int) -> Listing | None:
    stmt = listing_query().where(Listing.id == listing_id)
    return session.scalar(stmt)


def record_price_history(
    session: Session,
    *,
    listing: Listing,
    price: Decimal | None,
    price_text: str | None,
    unit_price_text: str | None,
) -> None:
    latest = listing.price_history[0] if listing.price_history else None
    if latest and latest.price == price and latest.price_text == price_text and latest.unit_price_text == unit_price_text:
        return
    session.add(
        PriceHistory(
            listing=listing,
            price=price,
            price_text=price_text,
            unit_price_text=unit_price_text,
        )
    )


def upsert_scraped_result(session: Session, result: ProductPrice) -> Listing:
    store = ensure_store(session, result.store)
    normalized_title = normalize_text(result.title or result.keyword)
    listing = session.scalar(
        select(Listing).where(
            Listing.store_id == store.id,
            Listing.title == (result.title or result.keyword),
        )
    )
    if listing is None:
        listing = Listing(
            store=store,
            keyword=result.keyword,
            title=result.title or result.keyword,
            normalized_title=normalized_title,
        )
        session.add(listing)
        session.flush()

    listing.keyword = result.keyword
    listing.title = result.title or result.keyword
    listing.normalized_title = normalized_title
    listing.url = result.url
    listing.current_price = Decimal(str(result.price)) if result.price is not None else None
    listing.current_price_text = result.price_text
    listing.unit_price_text = result.unit_price_text
    listing.note = result.note
    listing.last_seen_at = utcnow()
    listing.updated_at = utcnow()

    record_price_history(
        session,
        listing=listing,
        price=listing.current_price,
        price_text=listing.current_price_text,
        unit_price_text=listing.unit_price_text,
    )
    return listing
