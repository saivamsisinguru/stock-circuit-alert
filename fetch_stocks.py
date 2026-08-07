import os
import yfinance as yf
from supabase import create_client
from nsetools import Nse

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MAX_PRICE = 500

def fetch_all_nse_symbols():
    """Returns a list of all NSE stock symbols (cleaned)."""
    nse = Nse()
    # get_stock_codes() returns a list; the first element is typically a header like 'SYMBOL'
    raw_list = nse.get_stock_codes()
    # Filter out empty strings and the header
    symbols = [s.strip() for s in raw_list if s and s.strip() and s.strip() != 'SYMBOL']
    return symbols

def fetch_previous_closes(symbols, batch_size=200):
    """
    Fetch previous close prices using yfinance bulk download.
    Returns a list of dicts: [{'symbol': 'RELIANCE', 'prev_close': 1234.5}, ...]
    """
    tickers = [s + ".NS" for s in symbols]
    results = []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        try:
            data = yf.download(batch, period="5d", progress=False, threads=True)
            if data.empty:
                continue
            close = data['Close']
            # Take the second-last row (most recent completed day) as previous close
            if len(close) >= 2:
                prev_close_row = close.iloc[-2]
            else:
                prev_close_row = close.iloc[-1]
            for tkr, price in prev_close_row.items():
                if price and price <= MAX_PRICE:
                    sym = tkr.replace(".NS", "")
                    results.append({"symbol": sym, "prev_close": float(price)})
        except Exception as e:
            print(f"Batch {i} error: {e}")
    return results

def update_database(stocks):
    # Clear old records
    supabase.table("stocks_daily").delete().neq("symbol", "").execute()
    # Batch insert
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
        print("Fetching all NSE symbols...")
        symbols = fetch_all_nse_symbols()
        print(f"Total symbols: {len(symbols)}")
        print("Fetching previous close prices (this may take a few minutes)...")
        stocks = fetch_previous_closes(symbols)
        print(f"Found {len(stocks)} stocks with prev_close <= ₹{MAX_PRICE}")
        update_database(stocks)
    except Exception as e:
        print(f"Error: {e}")
        raise
