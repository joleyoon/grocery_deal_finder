from __future__ import annotations

from decimal import Decimal

from .models import Listing, PriceHistory, Store


def decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def serialize_store(store: Store) -> dict[str, object]:
    return {
        "id": store.id,
        "slug": store.slug,
        "name": store.name,
        "created_at": store.created_at.isoformat(),
    }


def serialize_listing(listing: Listing) -> dict[str, object]:
    return {
        "id": listing.id,
        "keyword": listing.keyword,
        "title": listing.title,
        "url": listing.url,
        "current_price": decimal_to_float(listing.current_price),
        "current_price_text": listing.current_price_text,
        "unit_price_text": listing.unit_price_text,
        "note": listing.note,
        "last_seen_at": listing.last_seen_at.isoformat(),
        "updated_at": listing.updated_at.isoformat(),
        "store": serialize_store(listing.store),
    }


def serialize_price_history(history: PriceHistory) -> dict[str, object]:
    return {
        "id": history.id,
        "listing_id": history.listing_id,
        "price": decimal_to_float(history.price),
        "price_text": history.price_text,
        "unit_price_text": history.unit_price_text,
        "observed_at": history.observed_at.isoformat(),
    }
