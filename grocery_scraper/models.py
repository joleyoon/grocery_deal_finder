from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class ProductPrice:
    store: str
    keyword: str
    title: str
    price_text: str | None = None
    price: float | None = None
    unit_price_text: str | None = None
    url: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
