from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Listing, PriceHistory
from .catalog import ensure_store, normalize_text


DEMO_ROWS = [
    {
        "store": "target",
        "keyword": "apple",
        "title": "Fresh Honeycrisp Apple - each",
        "price": Decimal("1.49"),
        "price_text": "$1.49",
        "unit_price_text": None,
        "url": "https://www.target.com/p/honeycrisp-apple-each/-/A-31167786",
    },
    {
        "store": "wholefoods",
        "keyword": "apple",
        "title": "Organic Honeycrisp Apple",
        "price": Decimal("3.99"),
        "price_text": "$3.99/lb",
        "unit_price_text": "$3.99/lb",
        "url": "https://www.wholefoodsmarket.com/grocery/product/fresh-produce-organic-honeycrisp-apple-b001gip2a8",
    },
    {
        "store": "traderjoes",
        "keyword": "apple",
        "title": "Sugar Bee Apple",
        "price": Decimal("2.99"),
        "price_text": "$2.99/12.7 Oz",
        "unit_price_text": "$2.99/12.7 Oz",
        "url": "https://www.traderjoes.com/home/products/pdp/sugar-bee-apple-078597",
    },
]


def seed_demo_data(session: Session) -> None:
    for row in DEMO_ROWS:
        store = ensure_store(session, row["store"])
        listing = session.scalar(
            select(Listing).where(
                Listing.store_id == store.id,
                Listing.title == row["title"],
            )
        )
        if listing is None:
            listing = Listing(
                store=store,
                keyword=row["keyword"],
                title=row["title"],
                normalized_title=normalize_text(row["title"]),
            )
            session.add(listing)
            session.flush()

        listing.keyword = row["keyword"]
        listing.title = row["title"]
        listing.normalized_title = normalize_text(row["title"])
        listing.url = row["url"]
        listing.current_price = row["price"]
        listing.current_price_text = row["price_text"]
        listing.unit_price_text = row["unit_price_text"]

        if not listing.price_history:
            session.add(
                PriceHistory(
                    listing=listing,
                    price=row["price"],
                    price_text=row["price_text"],
                    unit_price_text=row["unit_price_text"],
                )
            )
