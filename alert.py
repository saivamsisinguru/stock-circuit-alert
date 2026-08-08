import os
import yfinance as yf
import requests
from datetime import datetime, date, timedelta, timezone
from supabase import create_client
import pandas as pd

# ---------- CONNECT TO SUPABASE ----------
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- LOAD CONFIG FROM DB ----------
def load_config():
    res = supabase.table("config").select("*").execute()
    cfg = {}
    for row in res.data:
        cfg[row["key"]] = row["value"]
    return cfg

# ---------- SEND PUSH (edge function - topic based) ----------
def send_push(title, body):
    cfg = load_config()
    url = cfg.get("push_function_url")
    if not url:
        print("No push_function_url set, skipping push.")
        return

    try:
        resp = requests.post(url, json={
            "title": title,
            "body": body
        }, timeout=10)
        print(f"Push to topic: {resp.status_code} {resp.text[:80]}")
    except Exception as e:
        print(f"Push error: {e}")

# ---------- MARKET HOURS (IST) ----------
def is_market_open():
    utc_now = datetime.now(timezone.utc)
    ist = utc_now + timedelta(hours=5, minutes=30)
    if ist.weekday() >= 5:
        return False
    start = ist.replace(hour=9, minute=15, second=0, microsecond=0)
    end   = ist.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= ist <= end

# ---------- MAIN ALERT LOGIC ----------
def main():
    cfg = load_config()
    circuit_percent = int(cfg.get("circuit_percent", "20"))
    near_threshold  = int(cfg.get("near_threshold", "95"))
    max_price       = int(cfg.get("max_price", "500"))

    # TEMPORARY TEST – remove after successful push
    send_push("🚀 Test Alert", "Your stock alert system is working!")
    return

    if not is_market_open():
        print("Market closed, skipping.")
        return

    today_str = str(date.today())
    ist_time_str = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S")

    # ---- FETCH DAILY STOCK LIST (auto-discovered) ----
    print("Fetching stock list from stocks_daily...")
    try:
        db_stocks = supabase.table("stocks_daily").select("symbol, prev_close").execute().data
    except Exception as e:
        print(f"Error fetching stock list: {e}")
        return

    if not db_stocks:
        print("No stocks in stocks_daily. Run fetch_stocks.py first.")
        return

    stocks = {}
    for row in db_stocks:
        sym = row["symbol"].strip()
        prev = float(row["prev_close"])
        if prev <= max_price:
            stocks[sym] = prev

    if not stocks:
        print("All stocks filtered out.")
        return

    print(f"Loaded {len(stocks)} stocks under ₹{max_price}")

    tickers = [s + ".NS" for s in stocks.keys()]
    try:
        data = yf.download(tickers, period="1d", progress=False, threads=True)
    except Exception as e:
        print(f"Error downloading data: {e}")
        return

    if data.empty:
        print("No market data yet (maybe pre-open). Skipping.")
        return

    if len(tickers) == 1:
        close_prices = data['Close']
        current_prices = {tickers[0]: close_prices.iloc[-1]}
    else:
        close_prices = data['Close']
        current_prices = close_prices.iloc[-1].to_dict()

    for symbol, prev_close in stocks.items():
        ticker_key = symbol + ".NS"
        if ticker_key not in current_prices:
            continue

        curr = current_prices[ticker_key]
        if pd.isna(curr) or curr is None:
            continue

        try:
            curr = float(curr)
            prev_close = float(prev_close)

            if curr > max_price:
                continue

            upper = prev_close * (1 + circuit_percent / 100)
            lower = prev_close * (1 - circuit_percent / 100)
            upper_near = prev_close * (1 + circuit_percent / 100 * near_threshold / 100)
            lower_near = prev_close * (1 - circuit_percent / 100 * near_threshold / 100)

            db = supabase.table("circuit_alerts").select("*").eq("symbol", symbol).execute().data
            rec = db[0] if db else {}

            upper_suppress = False
            if rec.get("upper_circuit_open_date") != today_str:
                if curr >= upper:
                    supabase.table("circuit_alerts").upsert({"symbol": symbol, "upper_circuit_open_date": today_str}).execute()
                    upper_suppress = True
                else:
                    supabase.table("circuit_alerts").upsert({"symbol": symbol, "upper_circuit_open_date": "2000-01-01"}).execute()
            else:
                upper_suppress = (rec.get("upper_circuit_open_date") == today_str)

            lower_suppress = False
            if rec.get("lower_circuit_open_date") != today_str:
                if curr <= lower:
                    supabase.table("circuit_alerts").upsert({"symbol": symbol, "lower_circuit_open_date": today_str}).execute()
                    lower_suppress = True
                else:
                    supabase.table("circuit_alerts").upsert({"symbol": symbol, "lower_circuit_open_date": "2000-01-01"}).execute()
            else:
                lower_suppress = (rec.get("lower_circuit_open_date") == today_str)

            if curr >= upper_near and rec.get("last_upper_near_date") != today_str and not upper_suppress:
                send_push(f"🚀 {symbol} near UPPER circuit", f"₹{curr:.2f} (Upper: ₹{upper:.2f})")
                supabase.table("circuit_alerts").upsert({"symbol": symbol, "last_upper_near_date": today_str}).execute()

            if curr >= upper and rec.get("last_upper_hit_date") != today_str and not upper_suppress:
                send_push(f"🔴 {symbol} HIT upper circuit!", f"₹{curr:.2f}")
                supabase.table("circuit_alerts").upsert({"symbol": symbol, "last_upper_hit_date": today_str}).execute()

            if curr <= lower_near and rec.get("last_lower_near_date") != today_str and not lower_suppress:
                send_push(f"📉 {symbol} near LOWER circuit", f"₹{curr:.2f} (Lower: ₹{lower:.2f})")
                supabase.table("circuit_alerts").upsert({"symbol": symbol, "last_lower_near_date": today_str}).execute()

            if curr <= lower and rec.get("last_lower_hit_date") != today_str and not lower_suppress:
                send_push(f"🟢 {symbol} HIT lower circuit!", f"₹{curr:.2f}")
                supabase.table("circuit_alerts").upsert({"symbol": symbol, "last_lower_hit_date": today_str}).execute()

        except Exception as e:
            print(f"Error processing {symbol}: {e}")

if __name__ == "__main__":
    main()
