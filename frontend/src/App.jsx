import { startTransition, useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

const initialFilters = {
  query: "apple",
  store: "",
  inStock: false
};

const initialPurchase = {
  listingId: "",
  quantity: 1,
  purchaserName: "",
  note: ""
};

const initialInventory = {
  listingId: "",
  delta: 1,
  reason: "restock",
  actor: ""
};

function currency(value) {
  if (value === null || value === undefined) {
    return "N/A";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD"
  }).format(value);
}

function compactDate(value) {
  if (!value) {
    return "N/A";
  }
  return new Date(value).toLocaleString();
}

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

function StatusPill({ status, count }) {
  const tone =
    status === "in_stock" ? "pill-in" : status === "out_of_stock" ? "pill-out" : "pill-neutral";

  return (
    <span className={`status-pill ${tone}`}>
      {status.replaceAll("_", " ")} · {count}
    </span>
  );
}

function TrendBars({ history }) {
  const priced = history.filter((entry) => entry.price !== null);
  const max = Math.max(...priced.map((entry) => entry.price), 1);

  if (priced.length === 0) {
    return <div className="trend-empty">No price history yet.</div>;
  }

  return (
    <div className="trend-bars">
      {priced.slice(0, 8).reverse().map((entry) => (
        <div key={entry.id} className="trend-row">
          <span>{new Date(entry.observed_at).toLocaleDateString()}</span>
          <div className="trend-track">
            <div
              className="trend-fill"
              style={{ width: `${Math.max((entry.price / max) * 100, 8)}%` }}
            />
          </div>
          <strong>{currency(entry.price)}</strong>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [stores, setStores] = useState([]);
  const [filters, setFilters] = useState(initialFilters);
  const [results, setResults] = useState([]);
  const [comparison, setComparison] = useState({ offers: [], summary: {} });
  const [transactions, setTransactions] = useState([]);
  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState([]);
  const [purchaseForm, setPurchaseForm] = useState(initialPurchase);
  const [inventoryForm, setInventoryForm] = useState(initialInventory);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    async function bootstrap() {
      try {
        const [storesResponse, transactionsResponse] = await Promise.all([
          fetch(apiUrl("/api/stores")),
          fetch(apiUrl("/api/transactions?limit=6"))
        ]);
        const storesPayload = await storesResponse.json();
        const transactionsPayload = await transactionsResponse.json();
        startTransition(() => {
          setStores(storesPayload);
          setTransactions(transactionsPayload.items ?? []);
        });
        await runSearch(initialFilters);
      } catch (requestError) {
        setError(requestError.message);
      } finally {
        setLoading(false);
      }
    }

    bootstrap();
  }, []);

  async function runSearch(nextFilters = filters) {
    setLoading(true);
    setError("");
    setMessage("");

    const params = new URLSearchParams();
    if (nextFilters.query) {
      params.set("query", nextFilters.query);
    }
    if (nextFilters.store) {
      params.set("store", nextFilters.store);
    }
    if (nextFilters.inStock) {
      params.set("in_stock", "true");
    }
    params.set("limit", "30");

    try {
      const [productsResponse, comparisonResponse, transactionsResponse] = await Promise.all([
        fetch(apiUrl(`/api/products?${params.toString()}`)),
        fetch(apiUrl(`/api/compare?${params.toString()}`)),
        fetch(apiUrl("/api/transactions?limit=6"))
      ]);

      const [productsPayload, comparisonPayload, transactionsPayload] = await Promise.all([
        productsResponse.json(),
        comparisonResponse.json(),
        transactionsResponse.json()
      ]);

      if (!productsResponse.ok) {
        throw new Error(productsPayload.error || "Failed to load products");
      }
      if (!comparisonResponse.ok) {
        throw new Error(comparisonPayload.error || "Failed to load comparisons");
      }

      startTransition(() => {
        setResults(productsPayload.items ?? []);
        setComparison(comparisonPayload);
        setTransactions(transactionsPayload.items ?? []);
      });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function openDetail(listing) {
    setSelected(listing);
    setPurchaseForm((current) => ({
      ...current,
      listingId: String(listing.id),
      quantity: 1
    }));
    setInventoryForm((current) => ({
      ...current,
      listingId: String(listing.id),
      delta: listing.inventory_count === 0 ? 6 : 1
    }));

    try {
      const response = await fetch(apiUrl(`/api/products/${listing.id}`));
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Failed to load product detail");
      }
      startTransition(() => {
        setSelected(payload.item);
        setHistory(payload.history ?? []);
      });
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function syncLivePrices() {
    setSyncing(true);
    setError("");
    setMessage("");

    try {
      const response = await fetch(apiUrl("/api/scrapes"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          keyword: filters.query || "apple",
          stores: filters.store ? [filters.store] : undefined,
          limit: 8
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Failed to sync live prices");
      }
      setMessage(`Synced ${payload.count} live listings for "${payload.keyword}".`);
      await runSearch(filters);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSyncing(false);
    }
  }

  async function submitPurchase(event) {
    event.preventDefault();
    setError("");
    setMessage("");

    try {
      const response = await fetch(apiUrl("/api/transactions/purchases"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          listing_id: Number(purchaseForm.listingId),
          quantity: Number(purchaseForm.quantity),
          purchaser_name: purchaseForm.purchaserName,
          note: purchaseForm.note
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Failed to create purchase");
      }
      setMessage("Purchase transaction recorded.");
      setPurchaseForm((current) => ({ ...current, quantity: 1, note: "" }));
      await Promise.all([runSearch(filters), openDetail(payload.item)]);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function submitInventoryAdjustment(event) {
    event.preventDefault();
    setError("");
    setMessage("");

    try {
      const response = await fetch(apiUrl("/api/inventory/adjustments"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          listing_id: Number(inventoryForm.listingId),
          delta: Number(inventoryForm.delta),
          reason: inventoryForm.reason,
          actor: inventoryForm.actor
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Failed to adjust inventory");
      }
      setMessage("Inventory updated.");
      await Promise.all([runSearch(filters), openDetail(payload.item)]);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  const cheapestLabel = useMemo(() => {
    const cheapest = comparison.summary?.cheapest;
    if (!cheapest) {
      return "No priced offers yet";
    }
    return `${cheapest.store.name} · ${currency(cheapest.current_price)}`;
  }, [comparison]);

  return (
    <div className="app-shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />

      <header className="hero-panel reveal">
        <div className="hero-copy">
          <p className="eyebrow">Grocery Price Comparison Platform</p>
          <h1>Search prices, track shelf counts, and record purchases in one flow.</h1>
          <p className="hero-text">
            Flask powers the API, PostgreSQL-ready models store the catalog and history, Selenium
            collects live retailer data, and the React dashboard ties inventory and transactions
            together.
          </p>
        </div>

        <div className="hero-stats">
          <article className="metric-card">
            <span>Cheapest current offer</span>
            <strong>{cheapestLabel}</strong>
          </article>
          <article className="metric-card">
            <span>Visible listings</span>
            <strong>{results.length}</strong>
          </article>
          <article className="metric-card">
            <span>Recent transactions</span>
            <strong>{transactions.length}</strong>
          </article>
        </div>
      </header>

      <main className="dashboard-grid">
        <section className="panel reveal">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Search</p>
              <h2>Product search and live sync</h2>
            </div>
            <button className="accent-button" type="button" onClick={syncLivePrices} disabled={syncing}>
              {syncing ? "Syncing..." : "Sync Live Prices"}
            </button>
          </div>

          <form
            className="search-form"
            onSubmit={(event) => {
              event.preventDefault();
              runSearch(filters);
            }}
          >
            <label>
              Keyword
              <input
                value={filters.query}
                onChange={(event) =>
                  setFilters((current) => ({ ...current, query: event.target.value }))
                }
                placeholder="Try apple, yogurt, pasta..."
              />
            </label>

            <label>
              Store
              <select
                value={filters.store}
                onChange={(event) =>
                  setFilters((current) => ({ ...current, store: event.target.value }))
                }
              >
                <option value="">All stores</option>
                {stores.map((store) => (
                  <option key={store.id} value={store.slug}>
                    {store.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={filters.inStock}
                onChange={(event) =>
                  setFilters((current) => ({ ...current, inStock: event.target.checked }))
                }
              />
              In-stock only
            </label>

            <button className="primary-button" type="submit">
              Search
            </button>
          </form>

          {message ? <div className="flash success">{message}</div> : null}
          {error ? <div className="flash error">{error}</div> : null}
        </section>

        <section className="panel reveal">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Comparison</p>
              <h2>Cross-store pricing</h2>
            </div>
          </div>

          <div className="offer-grid">
            {(comparison.offers ?? []).slice(0, 3).map((offer) => (
              <article key={offer.id} className="offer-card">
                <span>{offer.store.name}</span>
                <strong>{currency(offer.current_price)}</strong>
                <p>{offer.title}</p>
                <small>{offer.unit_price_text || offer.current_price_text || "No unit price"}</small>
              </article>
            ))}
          </div>
        </section>

        <section className="panel panel-wide reveal">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Catalog</p>
              <h2>Listings and inventory</h2>
            </div>
            <span className="panel-caption">{loading ? "Loading..." : `${results.length} items`}</span>
          </div>

          <div className="listing-stack">
            {results.map((listing) => (
              <article key={listing.id} className="listing-card">
                <div>
                  <span className="listing-store">{listing.store.name}</span>
                  <h3>{listing.title}</h3>
                  <p className="listing-meta">{listing.unit_price_text || listing.current_price_text || "No unit price"}</p>
                </div>

                <div className="listing-side">
                  <strong>{currency(listing.current_price)}</strong>
                  <StatusPill status={listing.inventory_status} count={listing.inventory_count} />
                  <button className="ghost-button" type="button" onClick={() => openDetail(listing)}>
                    Manage
                  </button>
                </div>
              </article>
            ))}

            {!loading && results.length === 0 ? (
              <div className="empty-state">No listings matched this search.</div>
            ) : null}
          </div>
        </section>

        <aside className="panel detail-panel reveal">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Detail</p>
              <h2>{selected ? selected.title : "Select a listing"}</h2>
            </div>
          </div>

          {selected ? (
            <>
              <div className="detail-summary">
                <div>
                  <span>Current price</span>
                  <strong>{currency(selected.current_price)}</strong>
                </div>
                <div>
                  <span>Store</span>
                  <strong>{selected.store.name}</strong>
                </div>
                <div>
                  <span>Last updated</span>
                  <strong>{compactDate(selected.updated_at)}</strong>
                </div>
              </div>

              <TrendBars history={history} />

              <form className="stack-form" onSubmit={submitInventoryAdjustment}>
                <h3>Inventory adjustment</h3>
                <label>
                  Delta
                  <input
                    type="number"
                    value={inventoryForm.delta}
                    onChange={(event) =>
                      setInventoryForm((current) => ({ ...current, delta: event.target.value }))
                    }
                  />
                </label>
                <label>
                  Reason
                  <select
                    value={inventoryForm.reason}
                    onChange={(event) =>
                      setInventoryForm((current) => ({ ...current, reason: event.target.value }))
                    }
                  >
                    <option value="restock">restock</option>
                    <option value="cycle_count">cycle_count</option>
                    <option value="shrink">shrink</option>
                    <option value="manual_fix">manual_fix</option>
                  </select>
                </label>
                <label>
                  Actor
                  <input
                    value={inventoryForm.actor}
                    onChange={(event) =>
                      setInventoryForm((current) => ({ ...current, actor: event.target.value }))
                    }
                    placeholder="stock_manager"
                  />
                </label>
                <button className="primary-button" type="submit">
                  Update Inventory
                </button>
              </form>

              <form className="stack-form" onSubmit={submitPurchase}>
                <h3>Purchase transaction</h3>
                <label>
                  Quantity
                  <input
                    type="number"
                    min="1"
                    value={purchaseForm.quantity}
                    onChange={(event) =>
                      setPurchaseForm((current) => ({ ...current, quantity: event.target.value }))
                    }
                  />
                </label>
                <label>
                  Purchaser
                  <input
                    value={purchaseForm.purchaserName}
                    onChange={(event) =>
                      setPurchaseForm((current) => ({
                        ...current,
                        purchaserName: event.target.value
                      }))
                    }
                    placeholder="Jordan"
                  />
                </label>
                <label>
                  Note
                  <textarea
                    rows="3"
                    value={purchaseForm.note}
                    onChange={(event) =>
                      setPurchaseForm((current) => ({ ...current, note: event.target.value }))
                    }
                    placeholder="Optional purchase note"
                  />
                </label>
                <button className="accent-button" type="submit">
                  Record Purchase
                </button>
              </form>
            </>
          ) : (
            <div className="empty-state">
              Pick a listing to inspect its price trend, adjust inventory, or create a purchase transaction.
            </div>
          )}
        </aside>

        <section className="panel panel-wide reveal">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Ledger</p>
              <h2>Recent purchase transactions</h2>
            </div>
          </div>

          <div className="transaction-list">
            {transactions.map((transaction) => (
              <article key={transaction.id} className="transaction-card">
                <div>
                  <strong>{transaction.item.title}</strong>
                  <p>{transaction.item.store.name}</p>
                </div>
                <div>
                  <span>{transaction.quantity} units</span>
                  <strong>{currency(transaction.total_price)}</strong>
                </div>
                <small>{compactDate(transaction.created_at)}</small>
              </article>
            ))}

            {transactions.length === 0 ? (
              <div className="empty-state">No transactions recorded yet.</div>
            ) : null}
          </div>
        </section>
      </main>
    </div>
  );
}
