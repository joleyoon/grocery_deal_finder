from __future__ import annotations

import unittest

from grocery_scraper.cli import format_table
from grocery_scraper.models import ProductPrice
from grocery_scraper.utils import (
    extract_price_phrase,
    extract_unit_price,
    parse_price_value,
    text_after_title,
    title_matches_keyword,
)


class UtilsTests(unittest.TestCase):
    def test_extract_price_phrase_prefers_current_price(self) -> None:
        text = "Fresh Gala Apple $0.49 was $0.79 Add to cart"
        self.assertEqual(extract_price_phrase(text), "$0.49")

    def test_extract_price_phrase_supports_about_each_prices(self) -> None:
        text = "about $1.50 each $2.99/lb Large Opal Apple"
        self.assertEqual(extract_price_phrase(text), "about $1.50 each")

    def test_extract_price_phrase_prefers_shelf_price_over_unit_price(self) -> None:
        text = "$4.89($0.10/ounce) Fresh Fuji Apples - 3lb Bag"
        self.assertEqual(extract_price_phrase(text), "$4.89")

    def test_extract_price_phrase_does_not_truncate_unit_price(self) -> None:
        self.assertEqual(extract_price_phrase("$3.99/lb Organic Honeycrisp Apple"), "$3.99/lb")

    def test_extract_price_phrase_supports_package_size_suffix(self) -> None:
        self.assertEqual(extract_price_phrase("$6.49/12 Oz Uncured Apple Smoked Bacon"), "$6.49/12 Oz")

    def test_extract_unit_price(self) -> None:
        self.assertEqual(extract_unit_price("about $1.50 each $2.99/lb"), "$2.99/lb")

    def test_extract_unit_price_ignores_installment_text(self) -> None:
        self.assertIsNone(extract_unit_price("$39/mo Save 5%"))

    def test_parse_price_value(self) -> None:
        self.assertEqual(parse_price_value("about $1.50 each"), 1.5)

    def test_title_matches_keyword(self) -> None:
        self.assertTrue(title_matches_keyword("Organic Large Gala Apple - Each", "gala apple"))
        self.assertFalse(title_matches_keyword("Organic Pear - Each", "gala apple"))

    def test_title_matches_keyword_handles_simple_plurals(self) -> None:
        self.assertTrue(title_matches_keyword("Fresh Fuji Apples - 3lb Bag", "apple"))

    def test_text_after_title(self) -> None:
        text = "header Fresh Gala Apple $0.49 New lower price footer"
        window = text_after_title(text, "Fresh Gala Apple", window=25)
        self.assertEqual(window, "Fresh Gala Apple $0.49 Ne")

    def test_format_table(self) -> None:
        rendered = format_table(
            [
                ProductPrice(
                    store="target",
                    keyword="apple",
                    title="Fresh Gala Apple",
                    price_text="$0.49",
                    url="https://example.com",
                )
            ]
        )
        self.assertIn("Fresh Gala Apple", rendered)
        self.assertIn("$0.49", rendered)


if __name__ == "__main__":
    unittest.main()
