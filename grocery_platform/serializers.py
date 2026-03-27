from __future__ import annotations

from decimal import Decimal

from .models import InventoryAdjustment, Listing, PriceHistory, PurchaseTransaction, Store


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
        "inventory_count": listing.inventory_count,
        "inventory_status": listing.inventory_status,
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


def serialize_inventory_adjustment(adjustment: InventoryAdjustment) -> dict[str, object]:
    return {
        "id": adjustment.id,
        "listing_id": adjustment.listing_id,
        "delta": adjustment.delta,
        "reason": adjustment.reason,
        "actor": adjustment.actor,
        "resulting_quantity": adjustment.resulting_quantity,
        "created_at": adjustment.created_at.isoformat(),
    }


def serialize_purchase_transaction(transaction: PurchaseTransaction) -> dict[str, object]:
    return {
        "id": transaction.id,
        "listing_id": transaction.listing_id,
        "quantity": transaction.quantity,
        "unit_price": decimal_to_float(transaction.unit_price),
        "total_price": decimal_to_float(transaction.total_price),
        "purchaser_name": transaction.purchaser_name,
        "note": transaction.note,
        "created_at": transaction.created_at.isoformat(),
    }
