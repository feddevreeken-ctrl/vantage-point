"""
Debug: fetch the actual CAT Form 4 XML and print what's in it.
Also test parsing on a real filing to confirm the pipeline works end-to-end.
"""
import requests, re, xml.etree.ElementTree as ET

HEADERS = {"User-Agent": "VantagePoint Research fedde.vreeken@gmail.com"}

# CAT CIK and most recent Form 4
CAT_CIK = 18230
ACC = "0001104659-26-062809"  # filed 2026-05-15
acc_clean = ACC.replace("-", "")

# Step 1: get directory listing
dir_url = f"https://www.sec.gov/Archives/edgar/data/{CAT_CIK}/{acc_clean}/"
print(f"Directory: {dir_url}")
r = requests.get(dir_url, headers=HEADERS, timeout=10)
print(f"Status: {r.status_code}")

xml_files = re.findall(r'href="(/Archives/edgar/data/[^"]+\.xml)"', r.text)
print(f"XML files found: {xml_files}")

# Step 2: fetch and parse the Form 4 XML
for xml_path in xml_files:
    if "xsl" in xml_path.lower() or "index" in xml_path.lower():
        continue
    xml_url = "https://www.sec.gov" + xml_path
    print(f"\nFetching: {xml_url}")
    xr = requests.get(xml_url, headers=HEADERS, timeout=10)
    print(f"Status: {xr.status_code}, has ownershipDocument: {'<ownershipDocument' in xr.text}")
    if not xr.ok:
        continue

    # Parse XML
    root = ET.fromstring(xr.text)
    period = root.findtext(".//periodOfReport") or "?"
    rpt = root.find(".//reportingOwner")
    insider = rpt.findtext(".//rptOwnerName") if rpt else "?"
    rel = rpt.find(".//reportingOwnerRelationship") if rpt else None
    title_parts = []
    if rel is not None:
        if rel.findtext("isDirector") == "1": title_parts.append("Director")
        if rel.findtext("isOfficer") == "1": title_parts.append(rel.findtext("officerTitle") or "Officer")
    print(f"Period: {period}")
    print(f"Insider: {insider} / {', '.join(title_parts)}")

    for txn in root.findall(".//nonDerivativeTransaction"):
        code = (txn.findtext(".//transactionCode") or "").strip()
        shares_el = txn.find(".//transactionShares/value")
        price_el = txn.find(".//transactionPricePerShare/value")
        shares = int(float(shares_el.text)) if shares_el is not None and shares_el.text else 0
        price = float(price_el.text) if price_el is not None and price_el.text else 0
        value = shares * price
        print(f"  Transaction: code={code}  shares={shares}  price={price}  value=${value:,.0f}")

# Step 3: show what the top 20 most recent tracked buys look like across all sources
print("\n\n--- Checking what tickers have had REAL buys in last 30 days ---")
import json
txt = open("vp-data.js").read()
data = json.loads(txt[len("window.__VP_SNAPSHOT = "):-2])
buys = [t for t in data["transactions"] if t["type"] == "Buy" and t["filedDate"] <= 30]
buys.sort(key=lambda t: t["filedDate"])
print(f"Buys in last 30 days: {len(buys)}")
for b in buys[:20]:
    print(f"  {b['tradeDate']}  filed {b['filedDate']}d ago  {b['ticker']:6s}  {b['insider']:30s}  ${b['value']:>12,}")
