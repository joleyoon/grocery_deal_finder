from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select

from .db import get_session
from .models import Store
from .serializers import (
    serialize_listing,
    serialize_price_history,
    serialize_store,
)
from .services.catalog import (
    get_listing_or_404,
    search_listings,
    search_listings_cached,
    seed_stores,
)
from .services.collector import get_refresh_status


api = Blueprint("api", __name__, url_prefix="/api")


def bad_request(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code


def truthy_arg(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@api.get("/health")
def health():
    return jsonify({"status": "ok"})


@api.get("/stores")
def stores():
    session = get_session()
    seed_stores(session)
    session.commit()
    rows = session.scalars(select(Store).order_by(Store.name)).all()
    return jsonify([serialize_store(store) for store in rows])


@api.get("/products")
def products():
    session = get_session()
    query = request.args.get("query")
    store_slug = request.args.get("store")
    force_refresh = truthy_arg(request.args.get("refresh"))
    refresh_if_stale = truthy_arg(request.args.get("refresh_if_stale"))
    limit = min(int(request.args.get("limit", 50)), 100)
    stale_after_hours = int(current_app.config.get("STALE_QUERY_TTL_HOURS", 24))
    search_result = search_listings_cached(
        session,
        query=query,
        store_slug=store_slug,
        limit=limit,
        stale_after_hours=stale_after_hours,
        refresh_if_stale=refresh_if_stale or force_refresh,
        force_refresh=force_refresh,
        app=current_app._get_current_object(),
    )
    return jsonify(
        {
            "query": query,
            "count": len(search_result.items),
            "refreshed": search_result.refreshed,
            "refreshed_stores": search_result.refreshed_stores,
            "refresh_error": search_result.refresh_error,
            "refresh_mode": search_result.refresh_mode,
            "refresh_status": search_result.refresh_status,
            "stale_after_hours": stale_after_hours,
            "items": [serialize_listing(row) for row in search_result.items],
        }
    )


@api.get("/refresh-status")
def refresh_status():
    refresh_key = (request.args.get("key") or "").strip()
    if not refresh_key:
        return bad_request("key is required")
    status = get_refresh_status(current_app._get_current_object(), refresh_key)
    if status is None:
        return bad_request("refresh job not found", 404)
    return jsonify(status)


@api.get("/products/<int:listing_id>")
def product_detail(listing_id: int):
    session = get_session()
    listing = get_listing_or_404(session, listing_id)
    if listing is None:
        return bad_request("listing not found", 404)
    return jsonify(
        {
            "item": serialize_listing(listing),
            "history": [serialize_price_history(entry) for entry in listing.price_history[:12]],
        }
    )


@api.get("/compare")
def compare():
    session = get_session()
    query = request.args.get("query")
    if not query:
        return bad_request("query is required")
    rows = search_listings(
        session,
        query=query,
        store_slug=request.args.get("store"),
        limit=min(int(request.args.get("limit", 50)), 100),
    )
    priced_rows = [row for row in rows if row.current_price is not None]
    cheapest = min(priced_rows, key=lambda row: row.current_price) if priced_rows else None
    highest = max(priced_rows, key=lambda row: row.current_price) if priced_rows else None
    return jsonify(
        {
            "query": query,
            "offers": [serialize_listing(row) for row in priced_rows],
            "summary": {
                "offer_count": len(priced_rows),
                "cheapest": serialize_listing(cheapest) if cheapest else None,
                "highest": serialize_listing(highest) if highest else None,
            },
        }
    )
