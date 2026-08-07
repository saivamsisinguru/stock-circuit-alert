import csv
import io
import os
import requests
from supabase import create_client

# ---------- Supabase connection ----------
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MAX_PRICE = 500

def fetch_nse_bhavcopy():
    """
    Downloads the latest NSE bhavcopy CSV from the official NSE website.
    Returns a list of dicts with keys: symbol, prev_close
    """
    url = "https://www.nseindia.com/api/reports?archives=%5B%7B%22name%22%3A%22Securities%20available%20for%20Trading%22%2C%22type%22%3A%22archives%22%2C%22category%22%3A%22capital-market%22%2C%22section%22%3A%22equity%22%7D%5D"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }
    
    # First get the latest bhavcopy download link
    resp = requests.get(url, headers=headers, timeout=30)
    data = resp.json()
    latest = data["data"][0]  # most recent
    csv_url = "https://www.nseindia.com" + latest["link"]
    
    # Download the CSV
    csv_resp = requests.get(csv_url, headers=headers, timeout=30)
    csv_content = csv_resp.text
    
    # Parse CSV
    reader = csv.DictReader(io.StringIO(csv_content))
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
    # Delete old records
    supabase.table("stocks_daily").delete().neq("symbol", "").execute()
    # Insert new ones in batches (Supabase free tier might have limits, but this is fine)
    for stock in stocks:
        supabase.table("stocks_daily").upsert({
            "symbol": stock["symbol"],
            "prev_close": stock["prev_close"],
            "updated_at": "now()"
        }).execute()
    print(f"Inserted {len(stocks)} stocks into stocks_daily.")

if __name__ == "__main__":
    try:
        stock_list = fetch_nse_bhavcopy()
        update_database(stock_list)
    except Exception as e:
        print(f"Error: {e}")
        raise
