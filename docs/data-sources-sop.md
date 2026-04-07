# Data Sources SOP

## 1. Scope

This SOP defines the currently supported data sources for the US-market version of the project.

The default universe is the `Magnificent 7`:

- AAPL
- MSFT
- GOOGL
- AMZN
- META
- NVDA
- TSLA

The default benchmark is `SPY`.

## 2. Approved Sources

| Source | Category | Purpose | Notes |
| --- | --- | --- | --- |
| `yfinance` | Market data | Daily OHLCV, price history, selected fundamentals | Primary source for local market and factor cache |
| `SEC EDGAR` | Filings | Company disclosure metadata and filing references | Primary source for official public filings |

## 3. Collection Rules

### 3.1 yfinance

Use `yfinance` for:

- daily OHLCV history
- latest close
- valuation and financial snapshot fields used by the quant service

Collection rules:

- cache to `data/market`
- cache fundamentals to `data/financials`
- avoid unnecessary repeated live pulls
- prefer cached files for tests and deterministic runs

### 3.2 SEC EDGAR

Use SEC submissions JSON for:

- recent filing lists
- filing date
- form type
- accession number
- primary document path
- filing URL construction

Collection rules:

- always send a valid `SEC_USER_AGENT`
- treat EDGAR as the system-of-record filing source
- prefer filing metadata and official links over third-party summaries

## 4. Normalization Rules

- stock codes use US tickers such as `AAPL`, `MSFT`, `NVDA`
- benchmark uses `SPY`
- filing source is normalized to `sec_edgar`
- filing document type is normalized to `filing`

## 5. Storage Rules

- raw normalized documents: `data/raw`
- market cache: `data/market`
- fundamentals cache: `data/financials`
- structured metadata: `Postgres`
- graph context: `Postgres`-backed lightweight graph tables
- vector retrieval: `Chroma`

## 6. Retrieval Policy

For research answers:

1. prefer SEC EDGAR evidence when a filing exists
2. use yfinance-backed quant fields for technical, valuation, and financial analysis
3. attach source and date labels to every final response

## 7. Testing Policy

- tests should not rely on live network access
- tests should use deterministic fixtures or monkeypatched data loaders
- live yfinance and EDGAR access should remain optional runtime behavior
