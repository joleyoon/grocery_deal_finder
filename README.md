# grocery_deal_finder

Selenium-based grocery scraper for:

- Target
- Whole Foods
- Trader Joe's

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
python3 -m grocery_scraper apple --stores target wholefoods
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

- Whole Foods is location-sensitive. The scraper does a best-effort store selection with `--zip` and `--wholefoods-store`, but that flow can break when the site changes.
- Trader Joe's, Whole Foods, and Target can all change their DOM structure at any time, so this scraper is intentionally built with broad fallback selectors and visible-text parsing instead of depending on one brittle class name.
- If a store blocks automation or hides pricing until a store is selected, the output will include a note instead of a price.
- Target treats the bare query `apple` as the Apple brand, so the scraper automatically disambiguates that one case to `apple fruit` to surface grocery apples instead.
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
