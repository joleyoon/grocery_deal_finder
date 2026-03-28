from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .db import get_session
from .models import Listing, PurchaseTransaction, Store
from .serializers import (
    serialize_inventory_adjustment,
    serialize_listing,
    serialize_price_history,
    serialize_purchase_transaction,
    serialize_store,
)
from .services.catalog import (
    apply_inventory_adjustment,
    create_purchase_transaction,
    get_listing_or_404,
    search_listings,
    seed_stores,
    upsert_scraped_result,
)
from .services.collector import collect_prices, refresh_query_if_stale


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
    in_stock_only = truthy_arg(request.args.get("in_stock"))
    refresh_if_stale = truthy_arg(request.args.get("refresh_if_stale"))
    limit = min(int(request.args.get("limit", 50)), 100)
    stale_after_hours = int(current_app.config.get("STALE_QUERY_TTL_HOURS", 24))
    refreshed_stores: list[str] = []
    refresh_error: str | None = None
    if refresh_if_stale and query:
        try:
            refreshed_stores = refresh_query_if_stale(
                session,
                query=query,
                store_slug=store_slug,
                limit=limit,
                stale_after_hours=stale_after_hours,
            )
        except Exception as exc:  # noqa: BLE001
            refresh_error = str(exc)
    rows = search_listings(
        session,
        query=query,
        store_slug=store_slug,
        in_stock_only=in_stock_only,
        limit=limit,
    )
    return jsonify(
        {
            "query": query,
            "count": len(rows),
            "refreshed": bool(refreshed_stores),
            "refreshed_stores": refreshed_stores,
            "refresh_error": refresh_error,
            "stale_after_hours": stale_after_hours,
            "items": [serialize_listing(row) for row in rows],
        }
    )


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
            "transactions": [
                serialize_purchase_transaction(entry)
                for entry in listing.transactions[:10]
            ],
        }
    )


@api.get("/products/<int:listing_id>/history")
def product_history(listing_id: int):
    session = get_session()
    listing = get_listing_or_404(session, listing_id)
    if listing is None:
        return bad_request("listing not found", 404)
    limit = min(int(request.args.get("limit", 20)), 100)
    return jsonify(
        {
            "listing_id": listing.id,
            "items": [
                serialize_price_history(entry)
                for entry in listing.price_history[:limit]
            ],
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
        in_stock_only=truthy_arg(request.args.get("in_stock")),
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


@api.get("/inventory")
def inventory():
    session = get_session()
    rows = search_listings(
        session,
        query=request.args.get("query"),
        store_slug=request.args.get("store"),
        in_stock_only=truthy_arg(request.args.get("in_stock")),
        limit=min(int(request.args.get("limit", 50)), 100),
    )
    return jsonify(
        {
            "count": len(rows),
            "items": [serialize_listing(row) for row in rows],
        }
    )


@api.post("/inventory/adjustments")
def inventory_adjustments():
    session = get_session()
    payload = request.get_json(silent=True) or {}
    listing_id = payload.get("listing_id")
    delta = payload.get("delta")
    reason = (payload.get("reason") or "").strip()
    actor = (payload.get("actor") or "").strip() or None
    if listing_id is None or delta is None or not reason:
        return bad_request("listing_id, delta, and reason are required")
    listing = get_listing_or_404(session, int(listing_id))
    if listing is None:
        return bad_request("listing not found", 404)
    try:
        adjustment = apply_inventory_adjustment(
            session,
            listing=listing,
            delta=int(delta),
            reason=reason,
            actor=actor,
        )
    except ValueError as exc:
        return bad_request(str(exc))
    session.commit()
    return jsonify(
        {
            "adjustment": serialize_inventory_adjustment(adjustment),
            "item": serialize_listing(listing),
        }
    ), 201


@api.get("/transactions")
def transactions():
    session = get_session()
    stmt = (
        select(PurchaseTransaction)
        .options(selectinload(PurchaseTransaction.listing).selectinload(Listing.store))
        .order_by(PurchaseTransaction.created_at.desc())
        .limit(min(int(request.args.get("limit", 50)), 100))
    )
    rows = session.scalars(stmt).all()
    return jsonify(
        {
            "count": len(rows),
            "items": [
                {
                    **serialize_purchase_transaction(row),
                    "item": serialize_listing(row.listing),
                }
                for row in rows
            ],
        }
    )


@api.post("/transactions/purchases")
def create_purchase():
    session = get_session()
    payload = request.get_json(silent=True) or {}
    listing_id = payload.get("listing_id")
    quantity = payload.get("quantity")
    if listing_id is None or quantity is None:
        return bad_request("listing_id and quantity are required")
    listing = get_listing_or_404(session, int(listing_id))
    if listing is None:
        return bad_request("listing not found", 404)
    try:
        transaction = create_purchase_transaction(
            session,
            listing=listing,
            quantity=int(quantity),
            purchaser_name=(payload.get("purchaser_name") or "").strip() or None,
            note=(payload.get("note") or "").strip() or None,
        )
    except ValueError as exc:
        return bad_request(str(exc))
    session.commit()
    return jsonify(
        {
            "transaction": serialize_purchase_transaction(transaction),
            "item": serialize_listing(listing),
        }
    ), 201


@api.post("/scrapes")
def scrapes():
    session = get_session()
    payload = request.get_json(silent=True) or {}
    keyword = (payload.get("keyword") or "").strip()
    if not keyword:
        return bad_request("keyword is required")
    stores = payload.get("stores") or ["target", "wholefoods", "traderjoes"]
    results = collect_prices(
        keyword=keyword,
        stores=stores,
        limit=min(int(payload.get("limit", 8)), 25),
        zip_code=(payload.get("zip_code") or "").strip() or None,
        wholefoods_store=(payload.get("wholefoods_store") or "").strip() or None,
        chrome_binary=(payload.get("chrome_binary") or "").strip() or None,
        show_browser=bool(payload.get("show_browser", False)),
        timeout=int(payload.get("timeout", 20)),
        pause_seconds=float(payload.get("pause_seconds", 1.0)),
    )
    upserted: list[Listing] = []
    for result in results:
        if not result.title and not result.price_text and result.note:
            continue
        upserted.append(upsert_scraped_result(session, result))
    session.commit()
    return jsonify(
        {
            "keyword": keyword,
            "count": len(upserted),
            "items": [serialize_listing(item) for item in upserted],
        }
    ), 201
