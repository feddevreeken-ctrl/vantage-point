# Vantage Point — Insider Intelligence Platform

> A real-time insider trading intelligence dashboard tracking corporate executives, directors, and US Congress members across 100+ tickers.

Built as a personal CV project by Fedde Vreeken (Erasmus University, Economics).

## What it does

- **The Tape** — live feed of insider buys and sells ranked by AI signal strength, cluster activity, and market-relative alpha
- **Cluster Alerts** — detects when 2+ insiders buy the same stock within 30 days (historically the strongest signal)
- **Politicians** — tracks US Congress member trades under the STOCK Act, filtered by committee and party
- **Deep Dive** — per-stock candlestick chart with insider markers, analyst targets, institutional holders, and earnings calendar
- **Signal Portfolio** — backtested conviction portfolio showing cumulative return vs sector ETF benchmark
- **Track Record** — full equity curve of insider-following strategy vs market
- **My Portfolio** — connect your Trading 212 pie via API or CSV export to see insider signals on your actual holdings

## Data sources

- **yfinance** — insider transactions, institutional holders, analyst targets, earnings dates
- **SEC EDGAR Form 4** — official insider filings via EDGAR submissions API (same-day updates)
- **HouseStockTrades API** — US Congress member disclosures under the STOCK Act
- **OpenInsider** — supplemental insider buy data

## Architecture

Single-file React 18 app (Babel standalone, no build step). All data pre-fetched by a Python pipeline and packaged as `vp-data.js`, served as a static file alongside `index.html`.

```
build_vp_snapshot.py   # Data pipeline: fetches, enriches, deduplicates all sources
index.html             # Full app — React 18 + LightweightCharts + CSS design system
vp-data.js             # Pre-built snapshot (~5MB) refreshed daily by GitHub Actions
```

## Auto-refresh

GitHub Actions runs `build_vp_snapshot.py` every day at 09:00 UTC, commits the new `vp-data.js`, and Vercel auto-deploys within seconds. No manual steps required.

## Stack

`Python` · `yfinance` · `SEC EDGAR API` · `React 18` · `TradingView LightweightCharts` · `Vercel` · `GitHub Actions`

## Research basis

Signal scoring is informed by academic literature on insider trading returns:
- Jeng, Metrick & Zeckhauser (2003) — insider purchases earn ~6% abnormal returns over 6 months
- Seyhun (1998) — cluster buys by multiple insiders are significantly more predictive than solo trades
- Cohen, Malloy & Pomorski (2012) — routine vs opportunistic insider trading distinction
