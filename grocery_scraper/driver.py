from __future__ import annotations

from pathlib import Path

from selenium import webdriver


def _default_chrome_binary() -> str | None:
    candidates = (
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def build_chrome_driver(
    *,
    headless: bool,
    page_load_timeout: int,
    chrome_binary: str | None = None,
) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1600,2400")
    options.add_argument("--disable-gpu")
    options.add_argument("--lang=en-US")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    resolved_binary = chrome_binary or _default_chrome_binary()
    if resolved_binary:
        options.binary_location = resolved_binary

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(page_load_timeout)
    driver.implicitly_wait(0)
    return driver
