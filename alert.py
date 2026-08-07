import os
import yfinance as yf
from datetime import datetime, date, timedelta
from supabase import create_client

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

# ---------- DUMMY PUSH (replace later) ----------
def send_push(title, body):
    print(f"PUSH: {title} | {body}")
    # In the next step, we'll call your Supabase Edge Function here

# ---------- MARKET HOURS (IST) ----------
def is_market_open():
    ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
    if ist.weekday() >= 5:
        return False
    start = ist.replace(hour=9, minute=15, second=0, microsecond=0)
    end   = ist.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= ist <= end

# ---------- MAIN ALERT LOGIC ----------
def main():
    cfg = load_config()
    stocks          = cfg.get("stocks", "RELIANCE.NS").split(",")
    circuit_percent = int(cfg.get("circuit_percent", "20"))
    near_threshold  = int(cfg.get("near_threshold", "95"))
    max_price       = int(cfg.get("max_price", "500"))

    if not is_market_open():
        print("Market closed, skipping.")
        return

    today_str = str(date.today())
    ist_time_str = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S")

    for symbol in stocks:
        symbol = symbol.strip()
        try:
            ticker = yf.Ticker(symbol)
            prev = ticker.info.get("previousClose")
            curr = ticker.info.get("regularMarketPrice") or ticker.info.get("currentPrice")
            if not prev or not curr:
                continue

            # Filter by max price
            if curr > max_price:
                print(f"{symbol} ₹{curr:.2f} > ₹{max_price}, skip.")
                continue

            upper = prev * (1 + circuit_percent / 100)
            lower = prev * (1 - circuit_percent / 100)
            upper_near = prev * (1 + circuit_percent / 100 * near_threshold / 100)
            lower_near = prev * (1 - circuit_percent / 100 * near_threshold / 100)

            # Fetch alert record
            db = supabase.table("circuit_alerts").select("*").eq("symbol", symbol).execute().data
            rec = db[0] if db else {}

            # ---------- OPEN AT CIRCUIT CHECK ----------
            # Upper
            upper_suppress = False
            if rec.get("upper_circuit_open_date") != today_str:
                if curr >= upper:
                    # opened at upper circuit
                    supabase.table("circuit_alerts").upsert({"symbol": symbol, "upper_circuit_open_date": today_str}).execute()
                    upper_suppress = True
                    print(f"{symbol} opened at upper circuit, suppressing upper alerts.")
                else:
                    supabase.table("circuit_alerts").upsert({"symbol": symbol, "upper_circuit_open_date": "2000-01-01"}).execute()
            else:
                # already checked, was it a circuit open today?
                upper_suppress = (rec.get("upper_circuit_open_date") == today_str)

            # Lower
            lower_suppress = False
            if rec.get("lower_circuit_open_date") != today_str:
                if curr <= lower:
                    supabase.table("circuit_alerts").upsert({"symbol": symbol, "lower_circuit_open_date": today_str}).execute()
                    lower_suppress = True
                    print(f"{symbol} opened at lower circuit, suppressing lower alerts.")
                else:
                    supabase.table("circuit_alerts").upsert({"symbol": symbol, "lower_circuit_open_date": "2000-01-01"}).execute()
            else:
                lower_suppress = (rec.get("lower_circuit_open_date") == today_str)

            # ---------- ALERTS ----------
            # Upper near
            if curr >= upper_near and not rec.get("last_upper_near_date") == today_str and not upper_suppress:
                send_push(f"🚀 {symbol} near UPPER circuit", f"₹{curr:.2f} (Upper: ₹{upper:.2f})")
                supabase.table("circuit_alerts").upsert({"symbol": symbol, "last_upper_near_date": today_str}).execute()

            # Upper hit
            if curr >= upper and not rec.get("last_upper_hit_date") == today_str and not upper_suppress:
                send_push(f"🔴 {symbol} HIT upper circuit!", f"₹{curr:.2f}")
                supabase.table("circuit_alerts").upsert({"symbol": symbol, "last_upper_hit_date": today_str}).execute()

            # Lower near
            if curr <= lower_near and not rec.get("last_lower_near_date") == today_str and not lower_suppress:
                send_push(f"📉 {symbol} near LOWER circuit", f"₹{curr:.2f} (Lower: ₹{lower:.2f})")
                supabase.table("circuit_alerts").upsert({"symbol": symbol, "last_lower_near_date": today_str}).execute()

            # Lower hit
            if curr <= lower and not rec.get("last_lower_hit_date") == today_str and not lower_suppress:
                send_push(f"🟢 {symbol} HIT lower circuit!", f"₹{curr:.2f}")
                supabase.table("circuit_alerts").upsert({"symbol": symbol, "last_lower_hit_date": today_str}).execute()

        except Exception as e:
            print(f"Error {symbol}: {e}")

if __name__ == "__main__":
    main()
