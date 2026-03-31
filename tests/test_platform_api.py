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
        self.app.extensions["collector_refresh_statuses"] = {}
        self.app.extensions["collector_inflight_refreshes"] = set()
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

    def set_refresh_status(
        self,
        refresh_key: str,
        *,
        state: str = "running",
        stores: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        now = utcnow()
        self.app.extensions["collector_refresh_statuses"][refresh_key] = {
            "key": refresh_key,
            "query": "apple",
            "stores": tuple(stores or ["target"]),
            "limit": 30,
            "state": state,
            "error": error,
            "created_at": now,
            "started_at": now,
            "finished_at": now if state in {"completed", "failed"} else None,
            "updated_at": now,
        }

    def test_products_endpoint_returns_seeded_items(self) -> None:
        response = self.client.get("/api/products?query=apple")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertGreaterEqual(payload["count"], 3)
        self.assertNotIn("inventory_count", payload["items"][0])
        self.assertNotIn("inventory_status", payload["items"][0])

    def test_products_endpoint_skips_refresh_when_cached_data_is_fresh(self) -> None:
        with (
            patch("grocery_platform.services.collector.collect_prices") as mock_collect,
            patch("grocery_platform.services.collector.schedule_query_refresh") as mock_schedule,
        ):
            response = self.client.get(
                "/api/products?query=apple&store=target&refresh_if_stale=true"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertFalse(payload["refreshed"])
        self.assertEqual(payload["refresh_mode"], "none")
        self.assertEqual(payload["refreshed_stores"], [])
        mock_collect.assert_not_called()
        mock_schedule.assert_not_called()

    def test_products_endpoint_schedules_background_refresh_for_stale_store(self) -> None:
        self.age_listing(1, hours=25)

        with (
            patch("grocery_platform.services.collector.schedule_query_refresh") as mock_schedule,
            patch("grocery_platform.services.collector.get_refresh_status") as mock_status,
        ):
            mock_schedule.return_value = ["target"]
            mock_status.return_value = {
                "key": "apple::target::25",
                "query": "apple",
                "stores": ["target"],
                "limit": 25,
                "state": "queued",
                "error": None,
                "created_at": utcnow().isoformat(),
                "started_at": None,
                "finished_at": None,
                "updated_at": utcnow().isoformat(),
            }
            response = self.client.get(
                "/api/products?query=apple&store=target&refresh_if_stale=true"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["refreshed"])
        self.assertEqual(payload["refresh_mode"], "background")
        self.assertEqual(payload["refreshed_stores"], ["target"])
        self.assertIsNone(payload["refresh_error"])
        self.assertEqual(payload["refresh_status"]["state"], "queued")
        self.assertEqual(payload["refresh_status"]["stores"], ["target"])
        self.assertGreaterEqual(payload["count"], 1)
        mock_schedule.assert_called_once()

    def test_products_endpoint_reads_through_on_cache_miss(self) -> None:
        with patch("grocery_platform.services.collector.collect_prices") as mock_collect:
            mock_collect.return_value = [
                ProductPrice(
                    store="target",
                    keyword="dragon fruit",
                    title="Dragon Fruit - each",
                    price_text="$3.49",
                    price=3.49,
                    url="https://example.com/dragon-fruit",
                )
            ]
            response = self.client.get("/api/products?query=dragon%20fruit")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["refreshed"])
        self.assertEqual(payload["refresh_mode"], "blocking")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["title"], "Dragon Fruit - each")
        mock_collect.assert_called_once()

    def test_products_endpoint_force_refresh_schedules_background_refresh(self) -> None:
        with (
            patch("grocery_platform.services.collector.schedule_query_refresh") as mock_schedule,
            patch("grocery_platform.services.collector.get_refresh_status") as mock_status,
        ):
            mock_schedule.return_value = ["target"]
            mock_status.return_value = {
                "key": "apple::target::25",
                "query": "apple",
                "stores": ["target"],
                "limit": 25,
                "state": "running",
                "error": None,
                "created_at": utcnow().isoformat(),
                "started_at": utcnow().isoformat(),
                "finished_at": None,
                "updated_at": utcnow().isoformat(),
            }
            response = self.client.get("/api/products?query=apple&store=target&refresh=true")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["refreshed"])
        self.assertEqual(payload["refresh_mode"], "background")
        self.assertEqual(payload["refreshed_stores"], ["target"])
        self.assertEqual(payload["refresh_status"]["state"], "running")
        mock_schedule.assert_called_once()

    def test_refresh_status_endpoint_returns_tracked_job(self) -> None:
        self.set_refresh_status("apple::target::25", state="running")

        response = self.client.get("/api/refresh-status?key=apple%3A%3Atarget%3A%3A25")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["key"], "apple::target::25")
        self.assertEqual(payload["state"], "running")
        self.assertEqual(payload["stores"], ["target"])

    def test_product_detail_returns_item_and_history_only(self) -> None:
        response = self.client.get("/api/products/1")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("item", payload)
        self.assertIn("history", payload)
        self.assertNotIn("transactions", payload)
        self.assertNotIn("inventory_count", payload["item"])
        self.assertNotIn("inventory_status", payload["item"])

    def test_removed_inventory_transaction_and_manual_scrape_routes_return_404(self) -> None:
        self.assertEqual(self.client.get("/api/inventory").status_code, 404)
        self.assertEqual(self.client.post("/api/inventory/adjustments", json={}).status_code, 404)
        self.assertEqual(self.client.get("/api/transactions").status_code, 404)
        self.assertEqual(self.client.post("/api/transactions/purchases", json={}).status_code, 404)
        self.assertEqual(self.client.post("/api/scrapes", json={"keyword": "apple"}).status_code, 404)
        self.assertEqual(self.client.get("/api/products/1/history").status_code, 404)


if __name__ == "__main__":
    unittest.main()
