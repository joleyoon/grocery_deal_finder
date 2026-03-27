from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from grocery_platform import create_app
from grocery_platform.db import Base, get_engine, get_session_factory
from grocery_platform.services.demo import seed_demo_data


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

    def test_products_endpoint_returns_seeded_items(self) -> None:
        response = self.client.get("/api/products?query=apple")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertGreaterEqual(payload["count"], 3)

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
