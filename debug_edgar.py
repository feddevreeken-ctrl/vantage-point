import requests, json

HEADERS = {"User-Agent": "VantagePoint Research fedde.vreeken@gmail.com"}

# Get ticker->CIK map
resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=HEADERS, timeout=20)
ticker_cik = {}
for entry in resp.json().values():
    sym = (entry.get("ticker") or "").upper()
    cik = str(entry.get("cik_str") or "").zfill(10)
    ticker_cik[sym] = cik

cat_cik = ticker_cik.get("CAT", "")
print(f"CAT CIK: {cat_cik}")

# Get recent Form 4s for CAT
sub = requests.get(f"https://data.sec.gov/submissions/CIK{cat_cik}.json", headers=HEADERS, timeout=15)
recent = sub.json().get("filings", {}).get("recent", {})
forms = recent.get("form", [])
accs = recent.get("accessionNumber", [])
dates = recent.get("filingDate", [])
form4s = [(a, d) for f, a, d in zip(forms, accs, dates) if f == "4"][:3]
print(f"Recent Form 4s: {form4s}")

# Test the index JSON approach on the most recent filing
for acc, date in form4s[:1]:
    acc_clean = acc.replace("-", "")
    cik_int = int(cat_cik)
    idx_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{acc}-index.json"
    print(f"\nFetching index: {idx_url}")
    r = requests.get(idx_url, headers=HEADERS, timeout=10)
    print(f"Status: {r.status_code}")
    if r.ok:
        data = r.json()
        items = data.get("directory", {}).get("item", [])
        print(f"Files in filing:")
        for item in items:
            print(f"  {item.get('name')} ({item.get('type')})")
        # Find XML
        xml_name = None
        for item in items:
            name = item.get("name", "")
            if name.endswith(".xml") and "-index" not in name and "xsl" not in name.lower():
                xml_name = name
                break
        if xml_name:
            xml_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{xml_name}"
            print(f"\nFetching XML: {xml_url}")
            xr = requests.get(xml_url, headers=HEADERS, timeout=10)
            print(f"Status: {xr.status_code}, has ownershipDocument: {'<ownershipDocument' in xr.text}")
            print(xr.text[:600])
