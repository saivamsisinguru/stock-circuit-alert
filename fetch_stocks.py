import os
import yfinance as yf
from supabase import create_client
from nsetools import Nse
import pandas as pd

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MAX_PRICE = 500
MIN_AVG_VOLUME = 50000  # shares per day (10-day average)

def fetch_all_nse_symbols():
    nse = Nse()
    raw_list = nse.get_stock_codes()
    symbols = [s.strip() for s in raw_list if s and s.strip() and s.strip() != 'SYMBOL']
    return symbols

def fetch_previous_closes_and_volume(symbols, batch_size=200):
    results = []
    for i in range(0, len(symbols), batch_size):
        batch = [s + ".NS" for s in symbols[i:i+batch_size]]
        try:
            data = yf.download(batch, period="10d", progress=False, threads=True)
            if data.empty:
                continue
            close = data['Close']
            volume = data['Volume']
            if close.ndim == 1:  # single stock
                prev_close = close.iloc[-1] if len(close) >= 1 else None
                avg_vol = volume.mean() if len(volume) > 0 else 0
                sym = batch[0].replace(".NS", "")
                if prev_close and prev_close <= MAX_PRICE and avg_vol >= MIN_AVG_VOLUME:
                    results.append({"symbol": sym, "prev_close": float(prev_close)})
            else:
                # Multiple stocks
                last_row_idx = -1 if len(close) >= 1 else 0
                prev_close_row = close.iloc[last_row_idx]
                avg_vol_series = volume.mean()
                for tkr in prev_close_row.index:
                    price = prev_close_row[tkr]
                    vol_avg = avg_vol_series[tkr] if tkr in avg_vol_series else 0
                    sym = tkr.replace(".NS", "")
                    if pd.notna(price) and price <= MAX_PRICE and vol_avg >= MIN_AVG_VOLUME:
                        results.append({"symbol": sym, "prev_close": float(price)})
        except Exception as e:
            print(f"Batch {i} error: {e}")
    return results

def update_database(stocks):
    supabase.table("stocks_daily").delete().neq("symbol", "").execute()
    batch = []
    for s in stocks:
        batch.append(s)
        if len(batch) >= 100:
            supabase.table("stocks_daily").upsert(batch).execute()
            batch = []
    if batch:
        supabase.table("stocks_daily").upsert(batch).execute()
    print(f"Inserted {len(stocks)} stocks into stocks_daily (volume ≥ {MIN_AVG_VOLUME}).")

if __name__ == "__main__":
    try:
        print("Fetching all NSE symbols...")
        symbols = fetch_all_nse_symbols()
        print(f"Total symbols: {len(symbols)}")
        print("Fetching previous close & avg volume (this may take a few minutes)...")
        stocks = fetch_previous_closes_and_volume(symbols)
        print(f"Found {len(stocks)} stocks with prev_close ≤ ₹{MAX_PRICE} and avg volume ≥ {MIN_AVG_VOLUME}")
        update_database(stocks)
    except Exception as e:
        print(f"Error: {e}")
        raise
