#!/usr/bin/env python3

import argparse
import ast
import difflib
import json
import math
import re
from datetime import datetime, timezone
from numbers import Number
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf


TRACKED_TICKERS = [
    # Mega-cap tech
    "NVDA", "MSFT", "AAPL", "GOOGL", "GOOG", "META", "AMZN", "TSLA", "AMD",
    "ORCL", "CRM", "AVGO", "NFLX", "PLTR", "UBER", "SNOW", "NET", "DDOG",
    "SHOP", "NOW", "ADBE", "INTC", "QCOM", "MU", "ARM", "AMAT", "LRCX",
    "PANW", "CRWD", "ZS", "OKTA", "HUBS", "TWLO", "GTLB",
    # Financials
    "JPM", "BAC", "GS", "WFC", "BLK", "V", "MA", "AXP", "MS", "C",
    "SCHW", "COF", "USB", "PNC", "TFC", "SPGI", "MCO", "ICE", "CME",
    # Healthcare / Biotech
    "LLY", "PFE", "JNJ", "MRK", "UNH", "ABBV", "VRTX", "ISRG", "BMY",
    "AMGN", "GILD", "REGN", "BIIB", "MRNA", "ILMN", "DXCM", "IDXX",
    "CVS", "HUM", "CI", "ELV", "MOH",
    # Energy
    "XOM", "CVX", "COP", "OXY", "SLB", "HAL", "MPC", "PSX", "VLO",
    "EOG", "PXD", "DVN",
    # Industrials / Defense
    "CAT", "RTX", "GE", "BA", "LMT", "NOC", "GD", "HII", "LHX",
    "HON", "MMM", "UPS", "FDX", "DE", "EMR",
    # Consumer
    "WMT", "HD", "COST", "KO", "DIS", "MCD", "SBUX", "NKE", "TGT",
    "LOW", "TJX", "BKNG", "MAR", "HLT", "YUM", "CMG",
    # Real Estate / Utilities
    "AMT", "PLD", "EQIX", "CCI", "SPG", "NEE", "DUK", "SO",
    # EU / International
    "ASML", "SAP", "AZN", "SHEL", "SPOT", "NVO", "NOVO-B.CO",
    "TSM", "BABA", "TCEHY",
    # Small/Mid high-signal
    "SMCI", "SOUN", "IONQ", "RKLB", "LUNR", "ASTS", "ACHR",
    "APP", "HOOD", "SOFI", "AFRM", "UPST",
]

SECTOR_ETFS = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Consumer": "XLY",
    "Communication": "XLC",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
}

MARKET_ETFS = {
    "US": "SPY",
    "EU": "VGK",
}

POLITICIAN_ALIASES = {
    # Democrats
    "Nancy Pelosi": "Nancy Pelosi",
    "Paul Pelosi": "Nancy Pelosi",
    "Josh Gottheimer": "Josh Gottheimer",
    "Ro Khanna": "Ro Khanna",
    "Susie Lee": "Susie Lee",
    "Lois Frankel": "Lois Frankel",
    "Sheldon Whitehouse": "Sheldon Whitehouse",
    "John Larson": "John B. Larson",
    "Daniel Goldman": "Daniel Goldman",
    "Raja Krishnamoorthi": "Raja Krishnamoorthi",
    "Debbie Wasserman Schultz": "Debbie Wasserman Schultz",
    "Mikie Sherrill": "Mikie Sherrill",
    "Dean Phillips": "Dean Phillips",
    "Jake Auchincloss": "Jake Auchincloss",
    # Republicans
    "Kevin Hern": "Kevin Hern",
    "Brian Mast": "Brian Mast",
    "Mark Green": "Mark Green",
    "Dan Crenshaw": "Daniel Crenshaw",
    "Pat Fallon": "Patrick Fallon",
    "Michael McCaul": "Michael McCaul",
    "Michael Guest": "Michael Guest",
    "Virginia Foxx": "Virginia Foxx",
    "Tom Cole": "Tom Cole",
    "Marjorie Taylor Greene": "Marjorie Taylor Greene",
    "Mike Collins": "Mike Collins",
    "Barry Moore": "Barry Moore",
    "Greg Steube": "Greg Steube",
    "David Valadao": "David Valadao",
    "Pete Sessions": "Pete Sessions",
    # Senators
    "Tommy Tuberville": "Tommy Tuberville",
    "Kelly Loeffler": "Kelly Loeffler",
    "Ron Johnson": "Ron Johnson",
    "Rick Scott": "Rick Scott",
    "Mark Warner": "Mark Warner",
    "John Hoeven": "John Hoeven",
}

RETURN_OFFSETS = {
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
}


def parse_const_array(source_text: str, name: str):
    match = re.search(rf"const {name} = \[(.*?)\n\];", source_text, re.S)
    if not match:
        raise ValueError(f"Could not find const {name}")
    block = re.sub(r"//.*", "", match.group(1))
    return ast.literal_eval("[" + block + "]")


def nearest_index(rows, date_str):
    for idx, row in enumerate(rows):
        if row[0] >= date_str:
            return idx
    return None


def calc_return(rows, date_str, offset):
    if not rows:
        return None
    idx = nearest_index(rows, date_str)
    if idx is None or idx + offset >= len(rows):
        return None
    start_close = rows[idx][4]
    end_close = rows[idx + offset][4]
    if not start_close:
        return None
    return round((end_close / start_close) - 1, 4)


def normalize_name(value):
    if value is None:
        return ""
    return str(value).strip().title()


def first_present(mapping, *keys):
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def extract_date(value):
    if value is None:
        return None
    if isinstance(value, list):
        return extract_date(value[0] if value else None)
    try:
        ts = pd.to_datetime(value, errors="coerce")
    except Exception:
        return None
    if pd.isna(ts):
        return None
    return ts.date().isoformat()


def safe_float(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return float(value)
    except Exception:
        return None


def safe_int(value):
    number = safe_float(value)
    if number is None:
        return None
    return int(round(number))


def resolve_politician_queries(politician_names):
    resolved = {}
    try:
        listing = requests.get(
            "https://www.housestocktrades.com/api/list/politicians/ALL",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        listing.raise_for_status()
        all_rows = listing.json()
    except Exception:
        return {name: POLITICIAN_ALIASES.get(name, name) for name in politician_names}

    available = [row.get("insider", "").strip() for row in all_rows if row.get("insider")]
    available_lower = {name.lower(): name for name in available}

    for display_name in politician_names:
        alias = POLITICIAN_ALIASES.get(display_name)
        if alias:
            resolved[display_name] = alias
            continue

        exact = available_lower.get(display_name.lower())
        if exact:
            resolved[display_name] = exact
            continue

        last_name = display_name.split()[-1].lower()
        last_name_matches = [name for name in available if name.lower().split()[-1] == last_name]
        if len(last_name_matches) == 1:
            resolved[display_name] = last_name_matches[0]
            continue

        close_matches = difflib.get_close_matches(display_name, available, n=1, cutoff=0.72)
        if close_matches:
            resolved[display_name] = close_matches[0]
            continue

        resolved[display_name] = display_name

    return resolved


def price_rows_for_download(df, symbol):
    try:
        sub = df[symbol].dropna()
    except Exception:
        return []
    rows = []
    for dt, row in sub.iterrows():
        rows.append([
            dt.strftime("%Y-%m-%d"),
            round(float(row["Open"]), 4),
            round(float(row["High"]), 4),
            round(float(row["Low"]), 4),
            round(float(row["Close"]), 4),
            int(row["Volume"]),
        ])
    return rows


def build_peer_map(company_map, tickers):
    peers = {}
    for ticker in tickers:
        current = company_map[ticker]
        pool = [
            row for row in company_map.values()
            if row["sector"] == current["sector"] and row["ticker"] != ticker
        ]
        pool.sort(key=lambda row: (abs(row["mcap"] - current["mcap"]), -row["mcap"]))
        peers[ticker] = [row["ticker"] for row in pool[:3]]
    return peers


def company_loader(ticker):
    result = {
        "ticker": ticker,
        "insiderTransactions": [],
        "institutions": [],
        "earnings": {},
        "analystTargets": {},
        "recommendations": {},
        "errors": [],
    }
    stock = yf.Ticker(ticker)

    try:
        insider_df = stock.insider_transactions
        if insider_df is not None and not insider_df.empty:
            insider_df = insider_df.copy()
            date_col = "Transaction Start Date" if "Transaction Start Date" in insider_df.columns else "Start Date"
            text_col = "Text" if "Text" in insider_df.columns else "Transaction"
            insider_col = "Insider" if "Insider" in insider_df.columns else None
            title_col = "Position" if "Position" in insider_df.columns else None
            shares_col = "Shares" if "Shares" in insider_df.columns else None
            value_col = "Value" if "Value" in insider_df.columns else None
            insider_df = insider_df[insider_df[date_col].notna()]
            if not insider_df.empty:
                insider_df[text_col] = insider_df[text_col].fillna("").astype(str)
                insider_df = insider_df[
                    insider_df[text_col].str.contains("Purchase|Sale", case=False, na=False)
                ]
                if not insider_df.empty:
                    if value_col:
                        insider_df[value_col] = pd.to_numeric(insider_df[value_col], errors="coerce")
                    if shares_col:
                        insider_df[shares_col] = pd.to_numeric(insider_df[shares_col], errors="coerce")
                    if value_col:
                        insider_df = insider_df[insider_df[value_col].fillna(0).abs() >= 50000]
                    insider_df = insider_df.sort_values(date_col, ascending=False)
                    recent_cutoff = pd.Timestamp(datetime.now().date()) - pd.Timedelta(days=1095)
                    insider_df = insider_df[pd.to_datetime(insider_df[date_col], errors="coerce") >= recent_cutoff].head(40)
                    result["insiderTransactions"] = [
                        {
                            "tradeDate": pd.to_datetime(row[date_col]).date().isoformat(),
                            "insider": normalize_name(row.get(insider_col) if insider_col else None),
                            "title": str(row.get(title_col) or "Insider").strip(),
                            "text": str(row.get(text_col) or "").strip(),
                            "shares": abs(safe_int(row.get(shares_col)) or 0),
                            "value": abs(safe_int(row.get(value_col)) or 0),
                        }
                        for _, row in insider_df.iterrows()
                    ]
    except Exception as exc:
        result["errors"].append(f"insiders: {exc}")

    try:
        holders_df = stock.institutional_holders
        if holders_df is not None and not holders_df.empty:
            holders_df = holders_df.copy().head(5)
            result["institutions"] = [
                {
                    "name": str(row.get("Holder") or "Unknown Holder"),
                    "pctHeld": round((safe_float(first_present(row, "pctHeld", "% Out")) or 0) * 100, 2),
                    "value": safe_int(row.get("Value")),
                }
                for _, row in holders_df.iterrows()
            ]
    except Exception as exc:
        result["errors"].append(f"holders: {exc}")

    try:
        calendar = stock.calendar if isinstance(stock.calendar, dict) else {}
        earnings_dates = stock.earnings_dates
        next_earnings = None
        prev_eps = None
        if earnings_dates is not None and not earnings_dates.empty:
            frame = earnings_dates.copy().sort_index(ascending=False)
            for idx, row in frame.iterrows():
                dt = pd.Timestamp(idx).date()
                if dt >= datetime.now().date() and next_earnings is None:
                    next_earnings = dt.isoformat()
                if pd.notna(row.get("Reported EPS")) and prev_eps is None:
                    prev_eps = float(row["Reported EPS"])
            if next_earnings is None:
                future_dates = [pd.Timestamp(idx).date().isoformat() for idx in frame.index if pd.Timestamp(idx).date() >= datetime.now().date()]
                next_earnings = future_dates[0] if future_dates else None

        result["earnings"] = {
            "date": next_earnings or extract_date(calendar.get("Earnings Date")),
            "eps_est": round(safe_float(calendar.get("Earnings Average")), 2) if safe_float(calendar.get("Earnings Average")) is not None else None,
            "eps_prev": round(prev_eps, 2) if prev_eps is not None else None,
            "rev_est": safe_int(calendar.get("Revenue Average")),
            "exdiv": extract_date(calendar.get("Ex-Dividend Date")),
            "dividend": extract_date(calendar.get("Dividend Date")),
        }
    except Exception as exc:
        result["errors"].append(f"earnings: {exc}")

    try:
        analyst_targets = stock.analyst_price_targets
        if isinstance(analyst_targets, dict):
            result["analystTargets"] = {
                key: round(float(value), 2)
                for key, value in analyst_targets.items()
                if isinstance(value, Number) and not math.isnan(float(value))
            }
    except Exception as exc:
        result["errors"].append(f"targets: {exc}")

    try:
        recs = stock.recommendations_summary
        if recs is not None and not recs.empty:
            row = recs.iloc[0].to_dict()
            result["recommendations"] = {
                key: int(value)
                for key, value in row.items()
                if key != "period" and pd.notna(value)
            }
    except Exception as exc:
        result["errors"].append(f"recommendations: {exc}")

    return result


def fetch_sec_edgar_form4(tracked_tickers, min_value=50000, days_back=730):
    """
    Fetch recent Form 4 filings directly from SEC EDGAR.
    Strategy:
      1. Look up CIK for each ticker via EDGAR company search
      2. Fetch submissions JSON to get recent Form 4 accession numbers
      3. Fetch & parse each Form 4 XML to extract transaction details
    Free, no auth required. User-Agent required.
    Rate limit: 10 req/sec — we sleep 0.12s between calls.
    """
    import time
    import xml.etree.ElementTree as ET

    print("  [SEC EDGAR] Fetching Form 4 filings via EDGAR submissions API...")
    HEADERS = {"User-Agent": "VantagePoint Research research@vantagepoint.app"}
    date_cutoff = (datetime.now().date() - pd.Timedelta(days=days_back)).isoformat()
    tracked_set = set(t.upper() for t in tracked_tickers)
    results = []

    # Step 1: ticker → CIK mapping via EDGAR company search tickers.json
    ticker_cik = {}
    try:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=HEADERS, timeout=20
        )
        if resp.ok:
            data = resp.json()
            for entry in data.values():
                sym = (entry.get("ticker") or "").upper()
                cik = str(entry.get("cik_str") or "").zfill(10)
                if sym and cik and sym in tracked_set:
                    ticker_cik[sym] = cik
            print(f"  [SEC EDGAR] Mapped {len(ticker_cik)} tickers to CIKs")
        time.sleep(0.15)
    except Exception as exc:
        print(f"  [SEC EDGAR] CIK lookup failed: {exc}")
        return results

    def parse_form4_xml(xml_text, ticker, cik):
        """Parse a Form 4 XML and return list of transaction dicts."""
        txns = []
        try:
            root = ET.fromstring(xml_text)
            ns = ""
            # Get reporter name
            rpt = root.find(".//reportingOwner")
            insider_name = ""
            title = "Insider"
            if rpt is not None:
                n = rpt.find(".//rptOwnerName")
                if n is not None and n.text:
                    insider_name = normalize_name(n.text.strip())
                rel = rpt.find(".//reportingOwnerRelationship")
                if rel is not None:
                    titles = []
                    if rel.findtext("isDirector") == "1": titles.append("Director")
                    if rel.findtext("isOfficer") == "1":
                        ot = rel.findtext("officerTitle") or "Officer"
                        titles.append(ot.strip())
                    if rel.findtext("isTenPercentOwner") == "1": titles.append("10% Owner")
                    title = " / ".join(titles) or "Insider"

            # Period of report
            period = root.findtext(".//periodOfReport") or ""
            try:
                trade_date = pd.to_datetime(period).date().isoformat()
            except Exception:
                trade_date = datetime.now().date().isoformat()

            if trade_date < date_cutoff:
                return txns

            # Non-derivative transactions
            for txn in root.findall(".//nonDerivativeTransaction"):
                code_el = txn.find(".//transactionCode")
                code = (code_el.text or "").strip() if code_el is not None else ""
                # P = purchase, S = sale
                if code not in ("P", "S"):
                    continue
                shares_el = txn.find(".//transactionShares/value")
                price_el = txn.find(".//transactionPricePerShare/value")
                try:
                    shares = abs(int(float(shares_el.text))) if shares_el is not None and shares_el.text else 0
                except Exception:
                    shares = 0
                try:
                    price = float(price_el.text) if price_el is not None and price_el.text else 0.0
                except Exception:
                    price = 0.0
                value = int(shares * price)
                if value < min_value:
                    continue
                txns.append({
                    "ticker": ticker,
                    "insider": insider_name,
                    "title": title,
                    "tradeDate": trade_date,
                    "shares": shares,
                    "value": value,
                    "price": round(price, 2),
                    "type": "Buy" if code == "P" else "Sell",
                    "text": "Purchase" if code == "P" else "Sale",
                    "source": "sec_edgar",
                })
        except Exception:
            pass
        return txns

    # Step 2: for each ticker, get recent Form 4 filings from submissions API
    processed = 0
    for ticker, cik in list(ticker_cik.items()):
        try:
            sub_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            resp = requests.get(sub_url, headers=HEADERS, timeout=15)
            time.sleep(0.12)
            if not resp.ok:
                continue
            sub = resp.json()

            # Get recent filings
            recent = sub.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            accessions = recent.get("accessionNumber", [])
            filing_dates = recent.get("filingDate", [])

            # Find Form 4 filings within date window
            form4_filings = [
                (acc, fdate)
                for form, acc, fdate in zip(forms, accessions, filing_dates)
                if form == "4" and fdate >= date_cutoff
            ]

            # Process up to 30 most recent Form 4 filings per company
            for acc, fdate in form4_filings[:30]:
                acc_clean = acc.replace("-", "")
                # Fetch the filing index to find the XML file
                idx_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{acc}-index.json"
                try:
                    idx_resp = requests.get(idx_url, headers=HEADERS, timeout=10)
                    time.sleep(0.12)
                    if not idx_resp.ok:
                        continue
                    idx_data = idx_resp.json()
                    # Find the .xml form 4 file
                    xml_file = None
                    for item in idx_data.get("directory", {}).get("item", []):
                        name = item.get("name", "")
                        if name.endswith(".xml") and not name.endswith("-index.xml"):
                            xml_file = name
                            break
                    if not xml_file:
                        continue
                    xml_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{xml_file}"
                    xml_resp = requests.get(xml_url, headers=HEADERS, timeout=10)
                    time.sleep(0.12)
                    if not xml_resp.ok:
                        continue
                    txns = parse_form4_xml(xml_resp.text, ticker, cik)
                    results.extend(txns)
                except Exception:
                    continue

            processed += 1
            if processed % 10 == 0:
                print(f"  [SEC EDGAR] Processed {processed}/{len(ticker_cik)} tickers, {len(results)} transactions so far...")
        except Exception as exc:
            continue

    results = [r for r in results if r.get("insider") and r.get("value", 0) >= min_value]
    print(f"  [SEC EDGAR] Total: {len(results)} Form 4 transactions from {processed} companies")
    return results


def fetch_openinsider_buys(tracked_tickers, min_value=50000, days_back=365):
    """
    Fetch from OpenInsider via their HTML table (they block CSV endpoint).
    Falls back gracefully if blocked.
    """
    print("  [OpenInsider] Attempting fetch (may be blocked by server)...")
    results = []
    try:
        from bs4 import BeautifulSoup
        tracked_set = set(t.upper() for t in tracked_tickers)
        # Try their latest buys page
        url = f"https://openinsider.com/latest-insider-purchases-25k"
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=20,
        )
        if not resp.ok or len(resp.text) < 1000:
            print(f"  [OpenInsider] Blocked or empty ({resp.status_code})")
            return results
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", {"class": "tinytable"})
        if not table:
            print("  [OpenInsider] Table not found")
            return results
        rows = table.find_all("tr")[1:]  # skip header
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 11:
                continue
            try:
                ticker = cells[3].upper()
                if ticker not in tracked_set:
                    continue
                trade_date = pd.to_datetime(cells[1]).date().isoformat()
                insider_name = normalize_name(cells[5])
                title = cells[6]
                trade_type = cells[7]
                raw_val = cells[10].replace("$","").replace(",","").replace("+","").strip()
                value = abs(int(float(raw_val)))
                raw_shares = cells[9].replace(",","").replace("+","").strip()
                shares = abs(int(float(raw_shares)))
                if value < min_value:
                    continue
                is_buy = "P" in trade_type or "Purchase" in trade_type
                results.append({
                    "ticker": ticker,
                    "insider": insider_name,
                    "title": title,
                    "tradeDate": trade_date,
                    "shares": shares,
                    "value": value,
                    "type": "Buy" if is_buy else "Sell",
                    "text": "Purchase" if is_buy else "Sale",
                    "source": "openinsider",
                })
            except Exception:
                continue
        print(f"  [OpenInsider] Got {len(results)} qualifying transactions")
    except Exception as exc:
        print(f"  [OpenInsider] Failed: {exc}")
    return results


def build_snapshot(source_path: Path):
    source_text = source_path.read_text()
    cos = parse_const_array(source_text, "COS")
    pols = parse_const_array(source_text, "POLS")

    company_map = {
        ticker: {
            "ticker": ticker,
            "name": name,
            "market": market,
            "sector": sector,
            "mcap": mcap,
        }
        for ticker, name, market, sector, mcap in cos
    }
    politician_map = {
        name: {
            "name": name,
            "chamber": chamber,
            "party": party,
            "state": state,
            "committee": committee,
        }
        for name, chamber, party, state, committee in pols
    }
    politician_queries = resolve_politician_queries(list(politician_map))

    tracked = [ticker for ticker in TRACKED_TICKERS if ticker in company_map]
    peer_map = build_peer_map(company_map, tracked)

    price_symbols = set(tracked)
    for ticker in tracked:
        sector_etf = SECTOR_ETFS.get(company_map[ticker]["sector"])
        market_etf = MARKET_ETFS.get(company_map[ticker]["market"])
        if sector_etf:
            price_symbols.add(sector_etf)
        if market_etf:
            price_symbols.add(market_etf)

    price_download = yf.download(
        sorted(price_symbols),
        period="2y",
        interval="1d",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=False,
    )
    prices = {
        symbol: price_rows_for_download(price_download, symbol)
        for symbol in sorted(price_symbols)
    }
    prices = {symbol: rows for symbol, rows in prices.items() if rows}

    def perf_for(ticker, trade_date):
        company = company_map.get(ticker, {"sector": "Technology", "market": "US"})
        sector_etf = SECTOR_ETFS.get(company["sector"], "SPY")
        market_etf = MARKET_ETFS.get(company["market"], "SPY")
        peer_tickers = [peer for peer in peer_map.get(ticker, []) if peer in prices]
        result = {
            "sectorEtf": sector_etf,
            "marketEtf": market_etf,
            "peerTickers": peer_tickers,
        }
        stock_rows = prices.get(ticker, [])
        sector_rows = prices.get(sector_etf, [])
        market_rows = prices.get(market_etf, [])
        for label, offset in RETURN_OFFSETS.items():
            stock_ret = calc_return(stock_rows, trade_date, offset)
            sector_ret = calc_return(sector_rows, trade_date, offset)
            market_ret = calc_return(market_rows, trade_date, offset)
            peer_returns = [
                calc_return(prices.get(peer, []), trade_date, offset)
                for peer in peer_tickers
            ]
            peer_returns = [value for value in peer_returns if value is not None]
            peers_ret = round(sum(peer_returns) / len(peer_returns), 4) if peer_returns else None
            result[f"stock_{label}"] = stock_ret
            result[f"sector_{label}"] = sector_ret
            result[f"market_{label}"] = market_ret
            result[f"peers_{label}"] = peers_ret
            result[f"alphaSector_{label}"] = round(stock_ret - sector_ret, 4) if stock_ret is not None and sector_ret is not None else None
            result[f"alphaMarket_{label}"] = round(stock_ret - market_ret, 4) if stock_ret is not None and market_ret is not None else None
            result[f"alphaPeers_{label}"] = round(stock_ret - peers_ret, 4) if stock_ret is not None and peers_ret is not None else None
        return result

    company_results = {}
    # yfinance insider-transaction responses are noticeably more reliable when
    # fetched sequentially; parallel requests tended to hollow out the buy side.
    for ticker in tracked:
        result = company_loader(ticker)
        company_results[result["ticker"]] = result

    # ── Source 2: OpenInsider HTML scrape (broader coverage, more recent buys) ──
    print("\n[Phase 2] Fetching OpenInsider data...")
    oi_txns = fetch_openinsider_buys(tracked, min_value=50000, days_back=730)

    # ── Source 3: SEC EDGAR Form 4 XML (official filings, most authoritative) ──
    print("\n[Phase 3] Fetching SEC EDGAR Form 4 filings...")
    edgar_txns = fetch_sec_edgar_form4(tracked, min_value=50000, days_back=730)

    # Build dedup key: (ticker, insider_last_name, trade_date, type)
    seen_keys = set()

    def dedup_key(ticker, insider, trade_date, txn_type):
        last = (insider or "").split()[-1].lower() if insider else ""
        return (ticker, last, trade_date, txn_type)

    now = datetime.now().date()
    transactions = []
    next_id = 1

    # First pass: yfinance data (most reliable for value/shares)
    for ticker in tracked:
        payload = company_results.get(ticker, {})
        for row in payload.get("insiderTransactions", []):
            trade_date = row["tradeDate"]
            performance = perf_for(ticker, trade_date)
            filed_days = (now - pd.to_datetime(trade_date).date()).days
            type_label = "Buy" if "Purchase" in row["text"] else "Sell"
            price = round(row["value"] / row["shares"], 2) if row["shares"] else None
            company = company_map[ticker]
            dk = dedup_key(ticker, row["insider"], trade_date, type_label)
            seen_keys.add(dk)
            transactions.append({
                "id": next_id,
                "ticker": ticker,
                "company": company["name"],
                "market": company["market"],
                "sector": company["sector"],
                "mcap": company["mcap"],
                "insider": row["insider"],
                "title": row["title"],
                "isPolitician": False,
                "committee": None,
                "chamber": None,
                "party": None,
                "isLive": False,
                "type": type_label,
                "shares": row["shares"],
                "price": price,
                "value": row["value"],
                "filedDate": filed_days,
                "tradeDate": trade_date,
                "relationship": row["text"] or f"{type_label} Transaction",
                "is10b51": False,
                "shortInterest": None,
                "siTrend": None,
                "unusualOptions": False,
                "isForm144": False,
                "earningsProximity": False,
                "ret1w": performance["stock_1w"],
                "ret1m": performance["stock_1m"],
                "ret6m": performance["stock_6m"],
                "post30": performance["stock_1m"],
                "performance": performance,
                "source": "yfinance",
            })
            next_id += 1

    # Second pass: OpenInsider additions (not already in yfinance data)
    print(f"  Adding OpenInsider transactions (deduplicating against {len(seen_keys)} yfinance rows)...")
    oi_added = 0
    for row in oi_txns:
        ticker = row["ticker"]
        if ticker not in company_map:
            continue
        dk = dedup_key(ticker, row["insider"], row["tradeDate"], row["type"])
        if dk in seen_keys:
            continue  # already have this trade from yfinance
        seen_keys.add(dk)
        performance = perf_for(ticker, row["tradeDate"])
        filed_days = (now - pd.to_datetime(row["tradeDate"]).date()).days
        price = round(row["value"] / row["shares"], 2) if row.get("shares") and row["shares"] > 0 else None
        company = company_map[ticker]
        transactions.append({
            "id": next_id,
            "ticker": ticker,
            "company": company["name"],
            "market": company["market"],
            "sector": company["sector"],
            "mcap": company["mcap"],
            "insider": row["insider"],
            "title": row["title"],
            "isPolitician": False,
            "committee": None,
            "chamber": None,
            "party": None,
            "isLive": False,
            "type": row["type"],
            "shares": row.get("shares", 0),
            "price": price,
            "value": row["value"],
            "filedDate": filed_days,
            "tradeDate": row["tradeDate"],
            "relationship": row.get("text", f"{row['type']} Transaction"),
            "is10b51": False,
            "shortInterest": None,
            "siTrend": None,
            "unusualOptions": False,
            "isForm144": False,
            "earningsProximity": False,
            "ret1w": performance["stock_1w"],
            "ret1m": performance["stock_1m"],
            "ret6m": performance["stock_6m"],
            "post30": performance["stock_1m"],
            "performance": performance,
            "source": "openinsider",
        })
        next_id += 1
        oi_added += 1
    print(f"  Added {oi_added} new transactions from OpenInsider")

    # Third pass: SEC EDGAR additions (not already in yfinance or OpenInsider data)
    print(f"  Adding SEC EDGAR transactions (deduplicating against {len(seen_keys)} existing rows)...")
    edgar_added = 0
    for row in edgar_txns:
        ticker = row["ticker"]
        if ticker not in company_map:
            continue
        dk = dedup_key(ticker, row["insider"], row["tradeDate"], row["type"])
        if dk in seen_keys:
            continue  # already have this trade from earlier source
        seen_keys.add(dk)
        performance = perf_for(ticker, row["tradeDate"])
        filed_days = (now - pd.to_datetime(row["tradeDate"]).date()).days
        price = row.get("price") or (round(row["value"] / row["shares"], 2) if row.get("shares") and row["shares"] > 0 else None)
        company = company_map[ticker]
        transactions.append({
            "id": next_id,
            "ticker": ticker,
            "company": company["name"],
            "market": company["market"],
            "sector": company["sector"],
            "mcap": company["mcap"],
            "insider": row["insider"],
            "title": row["title"],
            "isPolitician": False,
            "committee": None,
            "chamber": None,
            "party": None,
            "isLive": False,
            "type": row["type"],
            "shares": row.get("shares", 0),
            "price": price,
            "value": row["value"],
            "filedDate": filed_days,
            "tradeDate": row["tradeDate"],
            "relationship": row.get("text", f"{row['type']} Transaction"),
            "is10b51": False,
            "shortInterest": None,
            "siTrend": None,
            "unusualOptions": False,
            "isForm144": False,
            "earningsProximity": False,
            "ret1w": performance["stock_1w"],
            "ret1m": performance["stock_1m"],
            "ret6m": performance["stock_6m"],
            "post30": performance["stock_1m"],
            "performance": performance,
            "source": "sec_edgar",
        })
        next_id += 1
        edgar_added += 1
    print(f"  Added {edgar_added} new transactions from SEC EDGAR")

    for display_name, query_name in politician_queries.items():
        try:
            response = requests.get(
                "https://www.housestocktrades.com/api/politician/" + requests.utils.quote(query_name),
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            response.raise_for_status()
            rows = response.json()
        except Exception:
            continue

        filtered = [row for row in rows if row.get("symbol") in tracked and row.get("trade_date")]
        filtered.sort(key=lambda row: pd.to_datetime(row["trade_date"], errors="coerce"), reverse=True)
        for row in filtered[:16]:
            ticker = row["symbol"]
            trade_date = pd.to_datetime(row["trade_date"]).date().isoformat()
            performance = perf_for(ticker, trade_date)
            ticker_rows = prices.get(ticker, [])
            idx = nearest_index(ticker_rows, trade_date)
            price = round(ticker_rows[idx][4], 2) if idx is not None else None
            value = int(row.get("buy_amount") or 0)
            shares = int(round(value / price)) if price and value else 0
            meta = politician_map.get(display_name, {
                "chamber": "House",
                "party": "D",
                "state": "US",
                "committee": "House disclosure",
            })
            company = company_map[ticker]
            transactions.append({
                "id": next_id,
                "ticker": ticker,
                "company": company["name"],
                "market": company["market"],
                "sector": company["sector"],
                "mcap": company["mcap"],
                "insider": display_name,
                "title": f"{meta['party']}-{meta['state']} · {meta['chamber']}",
                "isPolitician": True,
                "committee": meta.get("committee"),
                "chamber": meta.get("chamber"),
                "party": meta.get("party"),
                "isLive": False,
                "type": "Buy" if row.get("buy_or_sell") == "P" else "Sell",
                "shares": shares,
                "price": price,
                "value": value,
                "filedDate": (now - pd.to_datetime(trade_date).date()).days,
                "tradeDate": trade_date,
                "relationship": "House disclosure",
                "is10b51": False,
                "shortInterest": None,
                "siTrend": None,
                "unusualOptions": False,
                "isForm144": False,
                "earningsProximity": False,
                "ret1w": performance["stock_1w"],
                "ret1m": performance["stock_1m"],
                "ret6m": performance["stock_6m"],
                "post30": performance["stock_1m"],
                "performance": performance,
            })
            next_id += 1

    transactions.sort(key=lambda row: (row["filedDate"], -row["value"]))

    company_snapshots = {}
    for ticker in tracked:
        payload = company_results.get(ticker, {})
        latest_close = prices.get(ticker, [])[-1][4] if prices.get(ticker) else None
        company_snapshots[ticker] = {
            "price": latest_close,
            "institutions": payload.get("institutions", []),
            "earnings": payload.get("earnings", {}),
            "analystTargets": payload.get("analystTargets", {}),
            "recommendations": payload.get("recommendations", {}),
            "peerTickers": peer_map.get(ticker, []),
        }

    return {
        "meta": {
            "builtAt": datetime.now(timezone.utc).isoformat(),
            "source": "yfinance + OpenInsider + HouseStockTrades + SEC EDGAR",
            "transactionCount": len(transactions),
            "tickerCount": len({row["ticker"] for row in transactions}),
        },
        "companies": company_map,
        "politicians": politician_map,
        "prices": prices,
        "transactions": transactions,
        "companySnapshots": company_snapshots,
        "peerMap": peer_map,
        "sectorEtfs": SECTOR_ETFS,
        "marketEtfs": MARKET_ETFS,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    snapshot = build_snapshot(args.source)
    payload = "window.__VP_SNAPSHOT = " + json.dumps(snapshot, separators=(",", ":")) + ";\n"
    args.out.write_text(payload)
    print(f"Wrote {args.out} with {snapshot['meta']['transactionCount']} transactions across {snapshot['meta']['tickerCount']} tickers.")


if __name__ == "__main__":
    main()
