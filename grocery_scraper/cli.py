from __future__ import annotations

import argparse
import json
from typing import Iterable

from .driver import build_chrome_driver
from .models import ProductPrice
from .stores import ScraperSettings, build_scrapers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape grocery product prices across Target, Whole Foods, and Trader Joe's.",
    )
    parser.add_argument("keyword", help="Keyword to search for, for example: apple")
    parser.add_argument(
        "--stores",
        nargs="+",
        choices=("target", "wholefoods", "traderjoes"),
        default=("target", "wholefoods", "traderjoes"),
        help="Subset of stores to query.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum number of products to return per store.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="Per-page Selenium wait timeout in seconds.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=1.0,
        help="Short delay used after clicks and scrolls for dynamic pages.",
    )
    parser.add_argument(
        "--zip",
        dest="zip_code",
        help="Zip code used as a best-effort store selector for Whole Foods.",
    )
    parser.add_argument(
        "--wholefoods-store",
        help="Whole Foods store query, for example: 'Los Angeles, CA' or a zip code.",
    )
    parser.add_argument(
        "--chrome-binary",
        help="Optional path to the Chrome binary if Selenium cannot find it automatically.",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Run Chrome in headed mode instead of headless mode.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a table.",
    )
    return parser


def format_table(results: Iterable[ProductPrice]) -> str:
    rows = [
        [
            product.store,
            product.title or "-",
            product.price_text or "-",
            product.unit_price_text or "-",
            product.note or "-",
            product.url or "-",
        ]
        for product in results
    ]
    headers = ["store", "title", "price", "unit price", "note", "url"]
    widths = [
        max(len(str(value)) for value in [header, *column_values])
        for header, column_values in zip(headers, zip(*rows, strict=False), strict=False)
    ]

    def render_row(values: list[str]) -> str:
        return " | ".join(str(value).ljust(width) for value, width in zip(values, widths, strict=False))

    separator = "-+-".join("-" * width for width in widths)
    return "\n".join(
        [render_row(headers), separator, *(render_row(row) for row in rows)]
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = ScraperSettings(
        limit=args.limit,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
    )

    driver = build_chrome_driver(
        headless=not args.show_browser,
        page_load_timeout=args.timeout,
        chrome_binary=args.chrome_binary,
    )
    try:
        scrapers = build_scrapers(
            driver,
            settings,
            zip_code=args.zip_code,
            wholefoods_store=args.wholefoods_store,
        )

        all_results: list[ProductPrice] = []
        for store in args.stores:
            all_results.extend(scrapers[store].scrape(args.keyword))

        if args.json:
            print(
                json.dumps(
                    [result.to_dict() for result in all_results],
                    indent=2,
                )
            )
        else:
            print(format_table(all_results))
    finally:
        driver.quit()
    return 0
