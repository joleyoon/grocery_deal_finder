import { startTransition, useEffect, useMemo, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

const initialFilters = {
  query: "apple",
  store: ""
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
  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pendingRefresh, setPendingRefresh] = useState(null);
  const selectedRef = useRef(null);

  useEffect(() => {
    selectedRef.current = selected;
  }, [selected]);

  useEffect(() => {
    async function bootstrap() {
      try {
        const storesResponse = await fetch(apiUrl("/api/stores"));
        const storesPayload = await storesResponse.json();
        startTransition(() => {
          setStores(storesPayload);
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

  useEffect(() => {
    if (!pendingRefresh?.key) {
      return undefined;
    }

    let cancelled = false;
    let timeoutId;

    async function pollRefresh() {
      try {
        const response = await fetch(
          apiUrl(`/api/refresh-status?key=${encodeURIComponent(pendingRefresh.key)}`)
        );
        const payload = await response.json();

        if (cancelled) {
          return;
        }
        if (!response.ok) {
          throw new Error(payload.error || "Failed to check refresh status");
        }

        if (payload.state === "completed") {
          const refreshedStoreLabel = (payload.stores ?? []).join(", ");
          setPendingRefresh(null);
          await runSearch(pendingRefresh.filters, {
            preserveMessage: true,
            successMessage: refreshedStoreLabel
              ? `Background refresh complete for ${refreshedStoreLabel}.`
              : "Background refresh complete.",
            refreshSelectedDetail: Boolean(selectedRef.current)
          });
          return;
        }

        if (payload.state === "failed") {
          setPendingRefresh(null);
          setError(payload.error || "Background refresh failed.");
          return;
        }

        timeoutId = window.setTimeout(pollRefresh, 1500);
      } catch (requestError) {
        if (cancelled) {
          return;
        }
        setPendingRefresh(null);
        setError(requestError.message);
      }
    }

    timeoutId = window.setTimeout(pollRefresh, 1500);
    return () => {
      cancelled = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [pendingRefresh]);

  async function runSearch(nextFilters = filters, options = {}) {
    const {
      preserveMessage = false,
      successMessage = "",
      refreshSelectedDetail = false
    } = options;

    setPendingRefresh(null);
    setLoading(true);
    setError("");
    if (!preserveMessage) {
      setMessage("");
    }

    const params = new URLSearchParams();
    if (nextFilters.query) {
      params.set("query", nextFilters.query);
    }
    if (nextFilters.store) {
      params.set("store", nextFilters.store);
    }
    params.set("limit", "30");

    try {
      const productParams = new URLSearchParams(params);
      if (nextFilters.query) {
        productParams.set("refresh_if_stale", "true");
      }

      const productsResponse = await fetch(apiUrl(`/api/products?${productParams.toString()}`));
      const productsPayload = await productsResponse.json();

      if (!productsResponse.ok) {
        throw new Error(productsPayload.error || "Failed to load products");
      }

      const comparisonResponse = await fetch(apiUrl(`/api/compare?${params.toString()}`));
      const comparisonPayload = await comparisonResponse.json();
      if (!comparisonResponse.ok) {
        throw new Error(comparisonPayload.error || "Failed to load comparisons");
      }

      startTransition(() => {
        setResults(productsPayload.items ?? []);
        setComparison(comparisonPayload);
        if (productsPayload.refreshed_stores?.length) {
          if (productsPayload.refresh_mode === "background") {
            setMessage(
              `Refreshing ${productsPayload.refreshed_stores.join(", ")} in the background. Showing cached results for now.`
            );
          } else {
            setMessage(`Refreshed data for ${productsPayload.refreshed_stores.join(", ")}.`);
          }
        } else if (successMessage) {
          setMessage(successMessage);
        }
      });
      if (productsPayload.refresh_mode === "background" && productsPayload.refresh_status?.key) {
        setPendingRefresh({
          key: productsPayload.refresh_status.key,
          filters: nextFilters
        });
      }
      if (productsPayload.refresh_error) {
        setError(`Showing cached results. Auto-refresh failed: ${productsPayload.refresh_error}`);
      }
      if (refreshSelectedDetail && selectedRef.current) {
        await openDetail(selectedRef.current);
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function openDetail(listing) {
    setSelected(listing);

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
          <h1>Search prices, compare offers, and inspect recent price movement.</h1>
          <p className="hero-text">
            Flask powers the API, SQLAlchemy stores the catalog and price history, Selenium
            refreshes live retailer data when results go stale, and the React dashboard keeps the
            freshest available offers in view.
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
            <span>Tracked stores</span>
            <strong>{stores.length}</strong>
          </article>
        </div>
      </header>

      <main className="dashboard-grid">
        <section className="panel reveal">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Search</p>
              <h2>Product search</h2>
            </div>
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
              <h2>Listings</h2>
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
                  <button className="ghost-button" type="button" onClick={() => openDetail(listing)}>
                    Details
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
                <div>
                  <span>Last seen</span>
                  <strong>{compactDate(selected.last_seen_at)}</strong>
                </div>
              </div>

              <p className="listing-meta">
                {selected.unit_price_text || selected.current_price_text || "No unit pricing available"}
              </p>
              <TrendBars history={history} />
              {selected.note ? <p className="listing-meta">{selected.note}</p> : null}
              {selected.url ? (
                <a className="accent-button" href={selected.url} target="_blank" rel="noreferrer">
                  View Store Listing
                </a>
              ) : null}
            </>
          ) : (
            <div className="empty-state">
              Pick a listing to inspect its latest offer details and recent price trend.
            </div>
          )}
        </aside>
      </main>
    </div>
  );
}
