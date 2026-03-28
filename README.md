# Grocery Price Comparison Platform

Full-stack grocery comparison app with:

- Flask backend API
- React frontend
- PostgreSQL-ready persistence
- Selenium-based price collection

The platform lets you search products, compare prices across stores, track inventory, and record purchase transactions against current listings.

## Included Features

- Product search and filtering
- Price comparison across stores
- Inventory tracking on each listing
- Purchase transaction flow that decrements inventory
- REST API for search, comparison, inventory, transactions, and scrape ingestion
- Selenium ingestion path for Target, Whole Foods, and Trader Joe's

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
  - `InventoryAdjustment`
  - `PurchaseTransaction`
- Database URL via `DATABASE_URL`
- PostgreSQL-ready using `psycopg`
- SQLite fallback for quick local boot if `DATABASE_URL` is not set

## Frontend Stack

- React app in `frontend/src`
- Vite dev server with `/api` proxy to Flask
- Search dashboard with:
  - product search
  - comparison cards
  - inventory adjustment form
  - purchase transaction form
  - recent transaction ledger

## API Endpoints

- `GET /api/health`
- `GET /api/stores`
- `GET /api/products`
- `GET /api/products/<listing_id>`
- `GET /api/products/<listing_id>/history`
- `GET /api/compare`
- `GET /api/inventory`
- `POST /api/inventory/adjustments`
- `GET /api/transactions`
- `POST /api/transactions/purchases`
- `POST /api/scrapes`

## Transaction Flow

The implemented transaction flow is a purchase record:

1. Search or sync live listings.
2. Open a listing in the detail panel.
3. Record a purchase with quantity, purchaser name, and note.
4. The backend creates a `PurchaseTransaction` row and decrements tracked inventory using an `InventoryAdjustment`.

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

The backend can also ingest live prices:

```bash
curl -X POST http://127.0.0.1:5000/api/scrapes \
  -H "Content-Type: application/json" \
  -d '{"keyword":"apple","stores":["target","wholefoods","traderjoes"]}'
```

## Example API Calls

Search listings:

```bash
curl "http://127.0.0.1:5000/api/products?query=apple&in_stock=true"
```

Refresh stale cached results automatically during a product search:

```bash
curl "http://127.0.0.1:5000/api/products?query=apple&refresh_if_stale=true"
```

Compare offers:

```bash
curl "http://127.0.0.1:5000/api/compare?query=apple"
```

Adjust inventory:

```bash
curl -X POST http://127.0.0.1:5000/api/inventory/adjustments \
  -H "Content-Type: application/json" \
  -d '{"listing_id":1,"delta":12,"reason":"restock","actor":"stock_manager"}'
```

Create a purchase transaction:

```bash
curl -X POST http://127.0.0.1:5000/api/transactions/purchases \
  -H "Content-Type: application/json" \
  -d '{"listing_id":1,"quantity":2,"purchaser_name":"Jordan","note":"Weekend produce run"}'
```

## Notes

- The backend reuses the Selenium collector already in this repo rather than duplicating scraping logic.
- `GET /api/products?refresh_if_stale=true` will trigger Selenium only when matching store data is missing or older than 24 hours.
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
- `POST /api/inventory/adjustments`
- `POST /api/transactions/purchases`
- `GET /api/products/1/history`

Not verified in this environment:

- React build, because Node/NPM are not installed here
