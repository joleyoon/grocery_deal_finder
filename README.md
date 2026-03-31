# Grocery Price Comparison Platform

Full-stack grocery comparison app with:

- Flask backend API
- React frontend
- PostgreSQL-ready persistence
- Selenium-based price collection

The platform lets you search products, compare prices across stores, inspect recent price history, and refresh stale cached listings automatically.

## Included Features

- Product search and filtering
- Price comparison across stores
- Price-history detail view on each listing
- Read-through cache behavior with background refresh for stale results
- REST API for search, comparison, detail, store metadata, and refresh-status polling
- Selenium collection path for Target, Whole Foods, and Trader Joe's

## Repo Layout

```text
grocery_platform/      Flask app, models, services, and API routes
frontend/              React + Vite frontend
grocery_scraper/       Selenium collectors reused by the backend
scripts/               Debug helpers
tests/                 Existing scraper utility tests
```

## Backend Stack

- Flask app factory in `grocery_platform/app.py`
- SQLAlchemy models for:
  - `Store`
  - `Listing`
  - `PriceHistory`
- Database URL via `DATABASE_URL`
- PostgreSQL-ready using `psycopg`
- SQLite fallback for quick local boot if `DATABASE_URL` is not set

## Frontend Stack

- React app in `frontend/src`
- Vite dev server with `/api` proxy to Flask
- Search dashboard with:
  - product search
  - comparison cards
  - listing detail panel
  - price trend view
  - automatic stale-result refresh

## API Endpoints

- `GET /api/health`
- `GET /api/stores`
- `GET /api/products`
- `GET /api/refresh-status`
- `GET /api/products/<listing_id>`
- `GET /api/compare`

## Setup

### Python

```bash
python3 -m pip install -r requirements.txt
```

### Database

Copy `.env.example` to `.env` and set `DATABASE_URL` to PostgreSQL if you want a PostgreSQL-backed run:

```bash
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/grocery_price_platform
```

Initialize and seed:

```bash
flask --app grocery_platform.app:create_app init-db
flask --app grocery_platform.app:create_app seed-demo
```

### Backend Run

```bash
flask --app grocery_platform.app:create_app run --debug
```

### Frontend Run

Node is required for the React app:

```bash
cd frontend
npm install
npm run dev
```

### Selenium Collection

The old scraper CLI still works directly:

```bash
python3 -m grocery_scraper apple --json
```

## Example API Calls

Search listings:

```bash
curl "http://127.0.0.1:5000/api/products?query=apple"
```

Refresh stale cached results automatically during a product search:

```bash
curl "http://127.0.0.1:5000/api/products?query=apple&refresh_if_stale=true"
```

Force a refresh even when cached results are still fresh:

```bash
curl "http://127.0.0.1:5000/api/products?query=apple&refresh=true"
```

Compare offers:

```bash
curl "http://127.0.0.1:5000/api/compare?query=apple"
```

Fetch detail and recent price history for one listing:

```bash
curl "http://127.0.0.1:5000/api/products/1"
```

## Notes

- The backend reuses the Selenium collector already in this repo rather than duplicating scraping logic.
- `GET /api/products` behaves like a DB-backed read-through cache: cache misses scrape synchronously, upsert results, and then re-query.
- `GET /api/products?refresh_if_stale=true` returns cached rows immediately and refreshes stale or missing store results in the background.
- `GET /api/products?refresh=true` forces a background refresh when cached rows already exist.
- Background refreshes are tracked by `/api/refresh-status?key=...`, which the frontend polls so stale cached results are replaced automatically as soon as the scrape finishes.
- Whole Foods is location-sensitive and may need `zip_code` or `wholefoods_store` when scraping.
- Target treats the bare query `apple` as the Apple brand, so the scraper disambiguates that case to `apple fruit`.
- Trader Joe's broad search results can match many apple-adjacent products, so narrower produce queries work better for store-only produce comparisons.

## Verification

Verified in this environment:

```bash
python3 -m pip install -r requirements.txt
python3 -m compileall grocery_scraper grocery_platform tests scripts
python3 -m unittest discover -s tests
flask --app grocery_platform.app:create_app init-db
flask --app grocery_platform.app:create_app seed-demo
```

Also smoke-tested:

- `GET /api/stores`
- `GET /api/products?query=apple`
- `GET /api/compare?query=apple`
- `GET /api/products/1`
- `GET /api/refresh-status?key=...`

Not verified in this environment:

- React build, because Node/NPM are not installed here
