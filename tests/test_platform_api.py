from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from grocery_platform import create_app
from grocery_platform.db import Base, get_engine, get_session_factory
from grocery_platform.models import Listing, utcnow
from grocery_platform.services.demo import seed_demo_data
from grocery_scraper.models import ProductPrice


class PlatformApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tempdir = tempfile.TemporaryDirectory()
        database_path = Path(cls._tempdir.name) / "platform_test.db"
        cls.app = create_app(
            {
                "TESTING": True,
                "DATABASE_URL": f"sqlite:///{database_path}",
            }
        )
        cls.engine = get_engine(cls.app)
        cls.session_factory = get_session_factory(cls.app)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tempdir.cleanup()

    def setUp(self) -> None:
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        session = self.session_factory()
        try:
            seed_demo_data(session)
            session.commit()
        finally:
            session.close()

    def age_listing(self, listing_id: int, *, hours: int) -> None:
        session = self.session_factory()
        try:
            listing = session.get(Listing, listing_id)
            listing.last_seen_at = utcnow() - timedelta(hours=hours)
            listing.updated_at = listing.last_seen_at
            session.commit()
        finally:
            session.close()

    def test_products_endpoint_returns_seeded_items(self) -> None:
        response = self.client.get("/api/products?query=apple")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertGreaterEqual(payload["count"], 3)

    def test_products_endpoint_skips_refresh_when_cached_data_is_fresh(self) -> None:
        with patch("grocery_platform.services.collector.collect_prices") as mock_collect:
            response = self.client.get(
                "/api/products?query=apple&store=target&refresh_if_stale=true"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertFalse(payload["refreshed"])
        self.assertEqual(payload["refreshed_stores"], [])
        mock_collect.assert_not_called()

    def test_products_endpoint_refreshes_stale_store_when_requested(self) -> None:
        self.age_listing(1, hours=25)

        with patch("grocery_platform.services.collector.collect_prices") as mock_collect:
            mock_collect.return_value = [
                ProductPrice(
                    store="target",
                    keyword="apple",
                    title="Fresh Honeycrisp Apple - each",
                    price_text="$1.29",
                    price=1.29,
                    url="https://example.com/fresh-honeycrisp-apple",
                )
            ]
            response = self.client.get(
                "/api/products?query=apple&store=target&refresh_if_stale=true"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["refreshed"])
        self.assertEqual(payload["refreshed_stores"], ["target"])
        self.assertIsNone(payload["refresh_error"])
        mock_collect.assert_called_once()
        self.assertEqual(payload["items"][0]["current_price"], 1.29)

    def test_inventory_adjustment_updates_quantity(self) -> None:
        response = self.client.post(
            "/api/inventory/adjustments",
            json={
                "listing_id": 1,
                "delta": 2,
                "reason": "restock",
                "actor": "test_runner",
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["item"]["inventory_count"], 28)

    def test_purchase_transaction_decrements_inventory(self) -> None:
        response = self.client.post(
            "/api/transactions/purchases",
            json={
                "listing_id": 1,
                "quantity": 2,
                "purchaser_name": "test_runner",
                "note": "smoke transaction",
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["transaction"]["quantity"], 2)
        self.assertEqual(payload["item"]["inventory_count"], 24)


if __name__ == "__main__":
    unittest.main()
