import csv
import io
import os
from datetime import datetime, timedelta, timezone
import requests
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MAX_PRICE = 500

def get_last_trading_day():
    """Returns the last trading day (Monday-Friday) in IST."""
    utc_now = datetime.now(timezone.utc)
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    # If today is Monday, Friday might be 3 days ago; else yesterday if weekday
    if ist_now.weekday() == 0:
        days_back = 3
    elif ist_now.weekday() == 6:
        days_back = 2
    else:
        days_back = 1
    last_day = ist_now - timedelta(days=days_back)
    return last_day

def download_bhavcopy(date_obj):
    """
    Try to download the bhavcopy CSV for the given date (IST).
    Returns the file content as string if successful, else None.
    """
    # Format like: 07AUG2026
    day_str = date_obj.strftime("%d%b%Y").upper()
    year = date_obj.strftime("%Y")
    month = date_obj.strftime("%b").upper()  # e.g. AUG
    url = f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{year}/{month}/cm{day_str}bhav.csv.zip"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            # It's a ZIP, but often the CSV is inside. We'll try to extract it.
            from zipfile import ZipFile
            with ZipFile(io.BytesIO(resp.content)) as zf:
                # Find the CSV file inside
                for name in zf.namelist():
                    if name.endswith('.csv'):
                        return zf.read(name).decode('utf-8')
        else:
            # Fallback: try without .zip
            url_csv = f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{year}/{month}/cm{day_str}bhav.csv"
            resp2 = requests.get(url_csv, headers=headers, timeout=30)
            if resp2.status_code == 200:
                return resp2.text
    except Exception:
        pass
    return None

def fetch_nse_bhavcopy():
    """Retrieve the most recent bhavcopy and return symbols with prev_close <= MAX_PRICE."""
    last_trading_day = get_last_trading_day()
    content = None
    # Try last trading day, then previous days if not found
    for attempt in range(5):
        content = download_bhavcopy(last_trading_day)
        if content:
            break
        # Move one more day back (skip weekends manually, but we can just step back)
        last_trading_day -= timedelta(1)
        while last_trading_day.weekday() >= 5:  # skip weekends
            last_trading_day -= timedelta(1)

    if not content:
        raise Exception("Could not fetch bhavcopy for the last 5 trading days.")

    # Parse CSV
    reader = csv.DictReader(io.StringIO(content))
    stocks = []
    for row in reader:
        symbol = row.get("SYMBOL", "").strip()
        prev_close_str = row.get("PREV_CLOSE", "").replace(",", "").strip()
        if not symbol or not prev_close_str:
            continue
        try:
            prev_close = float(prev_close_str)
        except ValueError:
            continue
        if prev_close <= MAX_PRICE:
            stocks.append({"symbol": symbol, "prev_close": prev_close})

    return stocks

def update_database(stocks):
    # Clear existing data
    supabase.table("stocks_daily").delete().neq("symbol", "").execute()
    # Insert in batches (100 per call)
    batch = []
    for s in stocks:
        batch.append(s)
        if len(batch) >= 100:
            supabase.table("stocks_daily").upsert(batch).execute()
            batch = []
    if batch:
        supabase.table("stocks_daily").upsert(batch).execute()
    print(f"Inserted {len(stocks)} stocks into stocks_daily.")

if __name__ == "__main__":
    try:
        stock_list = fetch_nse_bhavcopy()
        update_database(stock_list)
    except Exception as e:
        print(f"Error: {e}")
        raise
