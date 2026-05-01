import time
import requests
import json
import hmac
import hashlib
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange

# ---------------- CONFIG ----------------
API_KEY = ""
API_SECRET = ""

BASE_URL = "https://api.crypto.com/exchange/v1/"
SYMBOL = "ETH_USDT"

TRADE_USD = 40
GRID_LEVELS = 6
SPACING = 0.005  # 0.5%

active_grid = {}
mode = "IDLE"

# ---------------- SIGNATURE ----------------
def sign(payload):
    msg = json.dumps(payload, separators=(',', ':'))
    return hmac.new(API_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()

def private_call(method, params):
    req = {
        "id": int(time.time()*1000),
        "method": method,
        "params": params,
        "api_key": API_KEY,
        "nonce": int(time.time()*1000)
    }
    req["sig"] = sign(req)
    return requests.post(BASE_URL, json=req).json()

# ---------------- MARKET DATA ----------------
def get_candles():
    r = requests.get(BASE_URL + "public/get-candlestick",
        params={"instrument_name": SYMBOL, "timeframe": "1m", "count": 100}
    ).json()

    df = pd.DataFrame(r["result"]["data"]).astype(float)
    return df

def get_price():
    r = requests.get(BASE_URL + "public/get-ticker").json()
    for d in r["result"]["data"]:
        if d["i"] == SYMBOL:
            return float(d["b"])

# ---------------- INDICATORS ----------------
def indicators(df):
    df["rsi"] = RSIIndicator(df["c"], 14).rsi()
    df["ema"] = EMAIndicator(df["c"], 50).ema_indicator()
    df["atr"] = AverageTrueRange(df["h"], df["l"], df["c"], 14).average_true_range()
    return df

# ---------------- ORDERS ----------------
def limit(side, price, qty):
    r = private_call("private/create-order", {
        "instrument_name": SYMBOL,
        "side": side,
        "type": "LIMIT",
        "price": str(price),
        "quantity": str(qty)
    })
    return r["result"]["order_id"]

def cancel(order_id):
    private_call("private/cancel-order", {"order_id": order_id})

# ---------------- GRID LOGIC ----------------
def create_grid(price, atr):
    global active_grid

    active_grid = {}
    spacing = max(atr / price, SPACING)
    qty = TRADE_USD / price

    print(f"Creating grid | spacing: {spacing:.4f}")

    for i in range(1, GRID_LEVELS + 1):
        buy_price = price * (1 - spacing * i)
        sell_price = price * (1 + spacing * i)

        b = limit("BUY", buy_price, qty)
        s = limit("SELL", sell_price, qty)

        active_grid[b] = "BUY"
        active_grid[s] = "SELL"

# ---------------- GRID CLEANUP ----------------
def clear_grid():
    global active_grid
    for oid in list(active_grid.keys()):
        try:
            cancel(oid)
        except:
            pass
    active_grid = {}

# ---------------- MAIN LOOP ----------------
print("Bot started...")

while True:
    try:
        df = indicators(get_candles())
        last = df.iloc[-1]

        price = last["c"]
        rsi = last["rsi"]
        ema = last["ema"]
        atr = last["atr"]

        print(f"Price:{price:.2f} RSI:{rsi:.1f} EMA:{ema:.2f} ATR:{atr:.2f} MODE:{mode}")

        # -------- RANGE MODE (GRID ON) --------
        if abs(price - ema) / ema < 0.01 and 35 < rsi < 65:
            if mode != "GRID":
                create_grid(price, atr)
                mode = "GRID"

        # -------- TREND MODE (GRID OFF) --------
        else:
            if mode == "GRID":
                clear_grid()
                mode = "TREND"

        time.sleep(15)

    except Exception as e:
        print("ERROR:", e)
        time.sleep(30)
