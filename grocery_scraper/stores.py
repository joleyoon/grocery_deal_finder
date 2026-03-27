from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from urllib.parse import quote

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    JavascriptException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from .models import ProductPrice
from .utils import (
    extract_price_phrase,
    extract_unit_price,
    normalize_whitespace,
    parse_price_value,
    text_after_title,
    title_matches_keyword,
    unique_in_order,
)


@dataclass(slots=True)
class ScraperSettings:
    limit: int
    timeout: int
    pause_seconds: float


class SiteScraper:
    store_name = "unknown"
    detail_url_markers: tuple[str, ...] = ()
    store_required_markers: tuple[tuple[str, str], ...] = (
        ("select a store to see accurate pricing", "store selection required for price"),
        ("find a store to see pricing", "store selection required for price"),
        ("choose a store to see pricing", "store selection required for price"),
    )

    def __init__(
        self,
        driver: WebDriver,
        settings: ScraperSettings,
        *,
        location_query: str | None = None,
    ) -> None:
        self.driver = driver
        self.settings = settings
        self.location_query = location_query

    def scrape(self, keyword: str) -> list[ProductPrice]:
        try:
            self.open_search(keyword)
            self.apply_location()
            direct_results = self.scrape_search_results(keyword)
            if direct_results is not None:
                if direct_results:
                    return direct_results[: self.settings.limit]
            links = self.collect_product_links(keyword)
        except Exception as exc:  # noqa: BLE001
            return [
                ProductPrice(
                    store=self.store_name,
                    keyword=keyword,
                    title="",
                    note=f"search failed: {exc}",
                )
            ]

        results: list[ProductPrice] = []
        for url in links:
            if len(results) >= self.settings.limit:
                break
            product = self.scrape_product(keyword, url)
            if product is None:
                continue
            results.append(product)

        if results:
            return results

        return [
            ProductPrice(
                store=self.store_name,
                keyword=keyword,
                title="",
                note="no matching products were found",
            )
        ]

    def open_search(self, keyword: str) -> None:
        self.driver.get(self.build_search_url(keyword))
        self.wait_for_page_ready()

    def build_search_url(self, keyword: str) -> str:
        raise NotImplementedError

    def apply_location(self) -> None:
        return None

    def scrape_search_results(self, keyword: str) -> list[ProductPrice] | None:
        del keyword
        return None

    def collect_product_links(self, keyword: str) -> list[str]:
        candidate_count = self.max_candidate_links()
        self.progressive_scroll()
        return self.extract_matching_links(candidate_count)

    def scrape_product(self, keyword: str, url: str) -> ProductPrice | None:
        try:
            self.driver.get(url)
            self.wait_for_page_ready()
            title = self.first_text(("//main//h1", "//h1"))
            if not title:
                return None

            page_text = self.first_text(("//main", "//*[@role='main']", "//body")) or ""
            if not self.is_relevant_product(title, page_text, keyword):
                return None
            price_window = text_after_title(page_text, title)
            price_text = extract_price_phrase(price_window) or extract_price_phrase(page_text)
            unit_price_text = extract_unit_price(price_window) or extract_unit_price(page_text)
            note = self.detect_note(page_text)
            if not price_text and note is None:
                note = "price not found; the site layout may have changed"

            return ProductPrice(
                store=self.store_name,
                keyword=keyword,
                title=title,
                price_text=price_text,
                price=parse_price_value(price_text),
                unit_price_text=unit_price_text,
                url=self.driver.current_url,
                note=note,
            )
        except Exception as exc:  # noqa: BLE001
            return ProductPrice(
                store=self.store_name,
                keyword=keyword,
                title="",
                url=url,
                note=f"product scrape failed: {exc}",
            )

    def is_relevant_product(self, title: str, page_text: str, keyword: str) -> bool:
        del page_text
        return title_matches_keyword(title, keyword)

    def max_candidate_links(self) -> int:
        return max(self.settings.limit * 4, self.settings.limit)

    def detect_note(self, page_text: str) -> str | None:
        lowered = page_text.lower()
        for marker, note in self.store_required_markers:
            if marker in lowered:
                return note
        return None

    def wait_for_page_ready(self) -> None:
        WebDriverWait(self.driver, self.settings.timeout).until(
            lambda current_driver: normalize_whitespace(
                current_driver.find_element(By.TAG_NAME, "body").text
            )
        )
        sleep(self.settings.pause_seconds)

    def progressive_scroll(self, iterations: int = 5) -> None:
        for _ in range(iterations):
            try:
                self.driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);"
                )
            except JavascriptException:
                return
            sleep(self.settings.pause_seconds)

    def extract_matching_links(self, limit: int) -> list[str]:
        hrefs: list[str] = []
        anchors = self.driver.find_elements(By.XPATH, "//a[@href]")
        for anchor in anchors:
            try:
                href = normalize_whitespace(anchor.get_attribute("href") or "")
            except StaleElementReferenceException:
                continue
            if not href or not href.startswith("http"):
                continue
            if self.detail_url_markers and not any(
                marker in href for marker in self.detail_url_markers
            ):
                continue
            hrefs.append(href.split("#", maxsplit=1)[0])
        return unique_in_order(hrefs)[:limit]

    def first_text(self, xpaths: tuple[str, ...]) -> str | None:
        for xpath in xpaths:
            elements = self.driver.find_elements(By.XPATH, xpath)
            for element in elements:
                try:
                    if not element.is_displayed():
                        continue
                    text = normalize_whitespace(element.text)
                except StaleElementReferenceException:
                    continue
                if text:
                    return text
        return None

    def visible_lines(self) -> list[str]:
        body = self.driver.find_element(By.TAG_NAME, "body").text
        return [normalize_whitespace(line) for line in body.splitlines() if normalize_whitespace(line)]

    def title_to_url(self, title: str) -> str | None:
        normalized_title = normalize_whitespace(title).lower()
        for anchor in self.driver.find_elements(By.XPATH, "//a[@href]"):
            try:
                anchor_text = normalize_whitespace(anchor.text)
                href = normalize_whitespace(anchor.get_attribute("href") or "")
            except StaleElementReferenceException:
                continue
            if not anchor_text or not href.startswith("http"):
                continue
            lowered = anchor_text.lower()
            if normalized_title == lowered or normalized_title in lowered:
                return href.split("#", maxsplit=1)[0]
        return None

    def parse_products_from_lines(
        self,
        keyword: str,
        *,
        context_before: int = 2,
        context_after: int = 3,
    ) -> list[ProductPrice]:
        lines = self.visible_lines()
        results: list[ProductPrice] = []
        seen_titles: set[str] = set()
        for index, line in enumerate(lines):
            if not title_matches_keyword(line, keyword):
                continue
            context = " ".join(
                lines[max(0, index - context_before) : min(len(lines), index + context_after + 1)]
            )
            price_text = extract_price_phrase(context)
            if not price_text:
                continue
            normalized_title = normalize_whitespace(line)
            if normalized_title in seen_titles:
                continue
            seen_titles.add(normalized_title)
            results.append(
                ProductPrice(
                    store=self.store_name,
                    keyword=keyword,
                    title=normalized_title,
                    price_text=price_text,
                    price=parse_price_value(price_text),
                    unit_price_text=extract_unit_price(context),
                    url=self.title_to_url(normalized_title),
                    note=None,
                )
            )
            if len(results) >= self.settings.limit:
                break
        return results

    def nearest_priced_parent_text(
        self,
        element: WebElement,
        *,
        max_depth: int = 5,
    ) -> str | None:
        current = element
        for _ in range(max_depth):
            try:
                current = current.find_element(By.XPATH, "./..")
            except Exception:  # noqa: BLE001
                return None
            text = normalize_whitespace(current.text)
            if text and extract_price_phrase(text):
                return text
        return None

    def click_first(self, xpaths: tuple[str, ...]) -> bool:
        for xpath in xpaths:
            elements = self.driver.find_elements(By.XPATH, xpath)
            for element in elements:
                if not self._is_visible(element):
                    continue
                self.scroll_into_view(element)
                try:
                    element.click()
                    sleep(self.settings.pause_seconds)
                    return True
                except (ElementClickInterceptedException, StaleElementReferenceException):
                    try:
                        self.driver.execute_script("arguments[0].click();", element)
                        sleep(self.settings.pause_seconds)
                        return True
                    except Exception:  # noqa: BLE001
                        continue
        return False

    def type_into_first(self, xpaths: tuple[str, ...], text: str) -> bool:
        for xpath in xpaths:
            elements = self.driver.find_elements(By.XPATH, xpath)
            for element in elements:
                if not self._is_visible(element):
                    continue
                if not element.is_enabled():
                    continue
                self.scroll_into_view(element)
                try:
                    element.click()
                    element.clear()
                    element.send_keys(text)
                    sleep(self.settings.pause_seconds)
                    return True
                except (ElementNotInteractableException, StaleElementReferenceException):
                    continue
        return False

    def scroll_into_view(self, element: WebElement) -> None:
        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )
        except JavascriptException:
            return

    @staticmethod
    def _is_visible(element: WebElement) -> bool:
        try:
            return element.is_displayed()
        except StaleElementReferenceException:
            return False


class TargetScraper(SiteScraper):
    store_name = "target"
    detail_url_markers = ("/p/",)
    grocery_markers = (
        "grocery",
        "produce",
        "fresh fruit",
        "fresh vegetables",
        "snack",
        "beverage",
        "pantry",
        "dairy",
        "frozen",
        "bakery",
        "meat",
        "seafood",
        "deli",
        "snap ebt",
    )

    def build_search_url(self, keyword: str) -> str:
        search_term = "apple fruit" if keyword.strip().lower() == "apple" else keyword
        return f"https://www.target.com/s?searchTerm={quote(search_term)}&category=5xt1a"

    def scrape_search_results(self, keyword: str) -> list[ProductPrice] | None:
        return self.parse_products_from_lines(keyword, context_before=1, context_after=3)

    def is_relevant_product(self, title: str, page_text: str, keyword: str) -> bool:
        if not title_matches_keyword(title, keyword):
            return False
        lowered = page_text.lower()
        return any(marker in lowered for marker in self.grocery_markers)

    def max_candidate_links(self) -> int:
        return max(self.settings.limit * 8, 32)


class WholeFoodsScraper(SiteScraper):
    store_name = "wholefoods"
    detail_url_markers = ("/product/",)

    def build_search_url(self, keyword: str) -> str:
        return "https://www.wholefoodsmarket.com/products/all-products"

    def open_search(self, keyword: str) -> None:
        self.driver.get(self.build_search_url(keyword))
        self.wait_for_page_ready()
        typed = self.type_into_first(
            (
                "//input[@name='search']",
                "//input[@placeholder='Search In-Store Products']",
                "//input[@aria-label='Search']",
            ),
            keyword,
        )
        if not typed:
            raise RuntimeError("Whole Foods search input not found")

        for xpath in (
            "//input[@name='search']",
            "//input[@aria-label='Search']",
        ):
            elements = self.driver.find_elements(By.XPATH, xpath)
            for element in elements:
                if self._is_visible(element):
                    element.send_keys(Keys.ENTER)
                    sleep(self.settings.pause_seconds * 2)
                    break
        self.progressive_scroll(iterations=2)

    def scrape_search_results(self, keyword: str) -> list[ProductPrice] | None:
        return self.parse_products_from_lines(keyword, context_before=0, context_after=3)

    def apply_location(self) -> None:
        if not self.location_query:
            return

        if not self.click_first(
            (
                "//button[contains(., 'Find a store')]",
                "//button[contains(., 'Select a store')]",
                "//a[contains(., 'Find a store')]",
            )
        ):
            return

        typed = self.type_into_first(
            (
                "//input[@type='search']",
                "//input[contains(translate(@placeholder, 'ZIPCITYSTATE', 'zipcitystate'), 'zip')]",
                "//input[contains(translate(@placeholder, 'ZIPCITYSTATE', 'zipcitystate'), 'city')]",
                "//input[contains(translate(@aria-label, 'STOREZIPCITY', 'storezipcity'), 'store')]",
            ),
            self.location_query,
        )
        if not typed:
            return

        for xpath in (
            "//input[@type='search']",
            "//input[contains(@aria-label, 'store')]",
        ):
            elements = self.driver.find_elements(By.XPATH, xpath)
            for element in elements:
                if self._is_visible(element):
                    element.send_keys(Keys.ENTER)
                    sleep(self.settings.pause_seconds * 2)
                    break

        self.click_first(
            (
                "//button[contains(., 'Set as store')]",
                "//button[contains(., 'Select store')]",
                "//button[contains(., 'Choose store')]",
                "//button[contains(., 'Shop this store')]",
            )
        )
        sleep(self.settings.pause_seconds * 2)
        self.open_search_keyword_again_if_possible()

    def open_search_keyword_again_if_possible(self) -> None:
        current_url = self.driver.current_url
        if "/products/all-products" in current_url:
            self.driver.get(current_url)
            self.wait_for_page_ready()


class TraderJoesScraper(SiteScraper):
    store_name = "traderjoes"
    detail_url_markers = ("/home/products/pdp/",)

    def build_search_url(self, keyword: str) -> str:
        return "https://www.traderjoes.com/home/products"

    def open_search(self, keyword: str) -> None:
        self.driver.get(self.build_search_url(keyword))
        self.wait_for_page_ready()
        self.click_first(("//button[contains(., 'GOT IT')]",))
        self.click_first(
            (
                "//button[contains(., 'Search Search')]",
                "//button[normalize-space(.)='Search']",
            )
        )

        search_inputs = self.driver.find_elements(
            By.XPATH,
            (
                "//input[contains(@placeholder, \"Search for your favorite Trader Joe's products\")]"
                " | //input[@type='search']"
                " | //input[@type='text']"
                " | //input[contains(@placeholder, 'Search')]"
                " | //input[contains(@aria-label, 'Search')]"
            ),
        )
        for search_input in search_inputs:
            if not self._is_visible(search_input):
                continue
            placeholder = normalize_whitespace(search_input.get_attribute("placeholder") or "")
            if placeholder in {"First Name", "Last Name", "Zip Code"}:
                continue
            search_input.clear()
            search_input.send_keys(keyword)
            search_input.send_keys(Keys.ENTER)
            self.click_first(("//button[normalize-space(.)='Search']",))
            WebDriverWait(self.driver, self.settings.timeout).until(
                lambda current_driver: (
                    "/home/search" in current_driver.current_url
                    or "results for"
                    in normalize_whitespace(
                        current_driver.find_element(By.TAG_NAME, "body").text
                    ).lower()
                )
            )
            sleep(self.settings.pause_seconds * 2)
            self.progressive_scroll()
            return
        raise RuntimeError("search input not found on Trader Joe's products page")

    def scrape_search_results(self, keyword: str) -> list[ProductPrice] | None:
        body_text = normalize_whitespace(self.driver.find_element(By.TAG_NAME, "body").text)
        results: list[ProductPrice] = []
        seen_titles: set[str] = set()
        cursor = 0
        for anchor in self.driver.find_elements(By.XPATH, "//a[@href]"):
            try:
                title = normalize_whitespace(anchor.text)
                href = normalize_whitespace(anchor.get_attribute("href") or "")
            except StaleElementReferenceException:
                continue
            if not title or title in seen_titles:
                continue
            if "/home/products/pdp/" not in href:
                continue
            if not title_matches_keyword(title, keyword):
                continue
            seen_titles.add(title)
            segment = self.nearest_priced_parent_text(anchor)
            if not segment:
                index = body_text.lower().find(title.lower(), cursor)
                if index >= 0:
                    cursor = index + len(title)
                segment = body_text[index : index + 200] if index >= 0 else title
            price_text = extract_price_phrase(segment)
            results.append(
                ProductPrice(
                    store=self.store_name,
                    keyword=keyword,
                    title=title,
                    price_text=price_text,
                    price=parse_price_value(price_text),
                    unit_price_text=extract_unit_price(segment),
                    url=href,
                    note=None if price_text else "price not found; the site layout may have changed",
                )
            )
            if len(results) >= self.settings.limit:
                break
        return results


def build_scrapers(
    driver: WebDriver,
    settings: ScraperSettings,
    *,
    zip_code: str | None,
    wholefoods_store: str | None,
) -> dict[str, SiteScraper]:
    return {
        "target": TargetScraper(driver, settings),
        "wholefoods": WholeFoodsScraper(
            driver,
            settings,
            location_query=wholefoods_store or zip_code,
        ),
        "traderjoes": TraderJoesScraper(driver, settings),
    }
