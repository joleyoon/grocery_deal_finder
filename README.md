# grocery_deal_finder

Selenium-based grocery scraper for:

- Target
- Whole Foods
- Trader Joe's
- Ralphs

It takes a keyword such as `apple` and returns matching products with prices when the site exposes them.

## Requirements

- Python 3.12+
- Google Chrome installed
- `selenium` Python package

## Install

```bash
python3 -m pip install -r requirements.txt
```

## Usage

Search all stores:

```bash
python3 -m grocery_scraper apple --json
```

Search a subset of stores:

```bash
python3 -m grocery_scraper apple --stores target ralphs
```

Use a zip code for location-sensitive stores:

```bash
python3 -m grocery_scraper apple --zip 90017
```

Run with the browser visible while debugging selectors:

```bash
python3 -m grocery_scraper apple --show-browser
```

## Notes

- Whole Foods and Ralphs are location-sensitive. The scraper does a best-effort store selection with `--zip`, `--wholefoods-store`, and `--ralphs-store`, but those flows can break when the sites change.
- Trader Joe's, Whole Foods, Target, and Ralphs can all change their DOM structure at any time, so this scraper is intentionally built with broad fallback selectors and visible-text parsing instead of depending on one brittle class name.
- If a store blocks automation or hides pricing until a store is selected, the output will include a note instead of a price.
- Target treats the bare query `apple` as the Apple brand, so the scraper automatically disambiguates that one case to `apple fruit` to surface grocery apples instead.
- Ralphs currently appears to block the headless Selenium session used by this project. If you need Ralphs working reliably, the next thing to try is running with `--show-browser` and refining that store's flow against a visible session.
- Trader Joe's search results can be broad for terms like `apple`, so a more specific query such as `honeycrisp apple` or `gala apple` will usually produce cleaner produce-only output.

## Output

The default output is a table with:

- `store`
- `title`
- `price`
- `unit price`
- `note`
- `url`

Use `--json` if you want structured output for another program.

## Local Checks

```bash
python3 -m compileall grocery_scraper tests
python3 -m unittest discover -s tests
```
