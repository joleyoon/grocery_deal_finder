from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, joinedload

from grocery_scraper.models import ProductPrice

from ..models import InventoryAdjustment, Listing, PriceHistory, PurchaseTransaction, Store, utcnow


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


def search_listings(
    session: Session,
    *,
    query: str | None,
    store_slug: str | None,
    in_stock_only: bool,
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
    if in_stock_only:
        stmt = stmt.where(Listing.inventory_count > 0)
    return list(session.scalars(stmt.limit(limit)))


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
            inventory_status="unknown",
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
    if listing.current_price_text and listing.inventory_status == "unknown":
        listing.inventory_status = "tracked"

    record_price_history(
        session,
        listing=listing,
        price=listing.current_price,
        price_text=listing.current_price_text,
        unit_price_text=listing.unit_price_text,
    )
    return listing


def apply_inventory_adjustment(
    session: Session,
    *,
    listing: Listing,
    delta: int,
    reason: str,
    actor: str | None,
) -> InventoryAdjustment:
    new_quantity = listing.inventory_count + delta
    if new_quantity < 0:
        raise ValueError("inventory adjustment would make quantity negative")
    listing.inventory_count = new_quantity
    listing.inventory_status = "in_stock" if new_quantity > 0 else "out_of_stock"
    listing.updated_at = utcnow()

    adjustment = InventoryAdjustment(
        listing=listing,
        delta=delta,
        reason=reason,
        actor=actor,
        resulting_quantity=new_quantity,
    )
    session.add(adjustment)
    return adjustment


def create_purchase_transaction(
    session: Session,
    *,
    listing: Listing,
    quantity: int,
    purchaser_name: str | None,
    note: str | None,
) -> PurchaseTransaction:
    if quantity <= 0:
        raise ValueError("quantity must be greater than zero")
    if listing.inventory_count < quantity:
        raise ValueError("inventory is too low for this purchase")

    unit_price = listing.current_price
    total_price = unit_price * quantity if unit_price is not None else None
    transaction = PurchaseTransaction(
        listing=listing,
        quantity=quantity,
        unit_price=unit_price,
        total_price=total_price,
        purchaser_name=purchaser_name,
        note=note,
    )
    session.add(transaction)
    apply_inventory_adjustment(
        session,
        listing=listing,
        delta=-quantity,
        reason="purchase",
        actor=purchaser_name,
    )
    return transaction
