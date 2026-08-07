import os
import yfinance as yf
from supabase import create_client
from nsetools import NSE

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MAX_PRICE = 500

def fetch_all_nse_symbols():
    """Returns a list of all NSE stock symbols."""
    nse = NSE()
    # get_stock_codes() returns a dict: {'SYMBOL': 'Company Name', ...}
    stock_dict = nse.get_stock_codes()
    # Remove the first key ('Symbol') and empty ones
    symbols = [s for s in stock_dict.keys() if s and s != 'Symbol']
    return symbols

def fetch_previous_closes(symbols, batch_size=200):
    """
    Fetch previous close prices using yfinance bulk download.
    Returns a list of dicts: [{'symbol': 'RELIANCE', 'prev_close': 1234.5}, ...]
    Only includes stocks with prev_close <= MAX_PRICE.
    """
    # Add .NS suffix for Yahoo Finance
    tickers = [s + ".NS" for s in symbols]
    results = []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        try:
            data = yf.download(batch, period="5d", progress=False, threads=True)
            if data.empty:
                continue
            # For each stock, get the previous close (yesterday's close)
            # data['Close'] contains the last row of each day, we want the second-last row (yesterday)
            # Simpler: use .info() but that's too many requests.
            # Instead, we'll use the last close of the previous day using historical data.
            # The dataframe index is dates; we can get the close of the last trading day.
            # yfinance returns data for the last 5 days, we can take the close of the day before today.
            # But today might be included if market is open; to be safe, we'll take the close of the second-last row (yesterday).
            close = data['Close']
            # Get the second-last row (index -2) which is the most recent complete day
            if len(close) >= 2:
                prev_close_row = close.iloc[-2]   # yesterday's close
            else:
                # Only one day? use that
                prev_close_row = close.iloc[-1]
            # prev_close_row is a Series with index = ticker (.NS)
            for tkr, price in prev_close_row.items():
                if price and price <= MAX_PRICE:
                    # Remove .NS suffix to get original symbol
                    sym = tkr.replace(".NS", "")
                    results.append({"symbol": sym, "prev_close": price})
        except Exception as e:
            print(f"Batch {i} error: {e}")
    return results

def update_database(stocks):
    # Clear old data
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
