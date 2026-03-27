from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import sleep

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grocery_scraper.driver import build_chrome_driver
from grocery_scraper.utils import normalize_whitespace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--output", default="tmp/debug_page.json")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--pause-seconds", type=float, default=2.0)
    parser.add_argument(
        "--click-text",
        action="append",
        default=[],
        help="Visible button text to click before dumping the page.",
    )
    parser.add_argument(
        "--search-text",
        help="Text to type into the first visible search-like input before dumping the page.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    driver = build_chrome_driver(headless=True, page_load_timeout=args.timeout)
    try:
        driver.get(args.url)
        sleep(args.pause_seconds)

        for click_text in args.click_text:
            candidates = driver.find_elements(
                By.XPATH,
                f"//button[contains(., {json.dumps(click_text)})] | //a[contains(., {json.dumps(click_text)})]",
            )
            for candidate in candidates:
                if not candidate.is_displayed():
                    continue
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", candidate
                )
                try:
                    candidate.click()
                except Exception:  # noqa: BLE001
                    driver.execute_script("arguments[0].click();", candidate)
                sleep(args.pause_seconds)
                break

        if args.search_text:
            inputs = driver.find_elements(
                By.XPATH,
                (
                    "//input[@type='search']"
                    " | //input[@type='text']"
                    " | //input[contains(@placeholder, 'Search')]"
                    " | //input[contains(@aria-label, 'Search')]"
                ),
            )
            for element in inputs:
                if not element.is_displayed() or not element.is_enabled():
                    continue
                placeholder = normalize_whitespace(element.get_attribute("placeholder") or "")
                if placeholder in {"First Name", "Last Name", "Zip Code"}:
                    continue
                try:
                    element.click()
                    element.clear()
                    element.send_keys(args.search_text)
                    element.send_keys(Keys.ENTER)
                    sleep(args.pause_seconds)
                    break
                except Exception:  # noqa: BLE001
                    continue

        data = {
            "url": driver.current_url,
            "title": driver.title,
            "inputs": [],
            "buttons": [],
            "anchors": [],
            "body_preview": normalize_whitespace(driver.find_element(By.TAG_NAME, "body").text)[:4000],
        }

        for element in driver.find_elements(By.XPATH, "//input")[:20]:
            data["inputs"].append(
                {
                    "type": element.get_attribute("type"),
                    "name": element.get_attribute("name"),
                    "placeholder": element.get_attribute("placeholder"),
                    "aria_label": element.get_attribute("aria-label"),
                }
            )

        for element in driver.find_elements(By.XPATH, "//button | //a")[:60]:
            text = normalize_whitespace(element.text)
            href = element.get_attribute("href")
            if not text and not href:
                continue
            target = data["buttons"] if element.tag_name == "button" else data["anchors"]
            target.append({"text": text, "href": href})

        output_path.write_text(json.dumps(data, indent=2))
        print(output_path)
    finally:
        driver.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
