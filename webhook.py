from flask import Flask, request, jsonify
from pybit.unified_trading import HTTP
from datetime import datetime
import threading
import time
import math
import os

app = Flask(__name__)

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "ZRyWx3GREmB9LQET4u")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "FzvPkH7tPuyDDZs0c7AAAskl1srtTvD4l8In")

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

TRAILING_PERCENT = 2.0
TRIGGER_PERCENT = 1.0
log_buffer = []

def get_step_size(symbol):
    try:
        info = session.get_instruments_info(category="linear", symbol=symbol)
        return float(info['result']['list'][0]['lotSizeFilter']['qtyStep'])
    except Exception as e:
        log_buffer.append(f"[StepSize ERROR] {str(e)}")
        return 0.01

def round_qty_to_step(qty, step):
    return math.floor(qty / step) * step

def monitor_price_and_set_trailing_stop(symbol, entry_price, side, qty):
    target_price = entry_price * (1 + TRIGGER_PERCENT / 100)
    trailing_side = "Sell" if side == "Buy" else "Buy"
    log_buffer.append(f"[Trailing] Monitoring {symbol}, Entry: {entry_price}, Target: {target_price}, Side: {side}")

    while True:
        try:
            ticker = session.get_tickers(category="linear", symbol=symbol)
            last_price = float(ticker["result"]["list"][0]["lastPrice"])
            log_buffer.append(f"[Trailing] Last Price: {last_price}")

            if (side == "Buy" and last_price >= target_price) or (side == "Sell" and last_price <= entry_price * (1 - TRIGGER_PERCENT / 100)):
                response = session.place_order(
                    category="linear",
                    symbol=symbol,
                    side=trailing_side,
                    order_type="TrailingStopMarket",
                    qty=qty,
                    time_in_force="GoodTillCancel",
                    reduce_only=True,
                    trigger_by="LastPrice",
                    trailing_stop=str(TRAILING_PERCENT)
                )
                timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                log_buffer.append(f"[{timestamp}] TRAILING STOP ACTIVATED: {response}")
                break
        except Exception as e:
            log_buffer.append(f"[Monitor ERROR] {str(e)}")
            break

        time.sleep(5)

@app.route('/', methods=['GET'])
def status():
    return "✅ Webhook Bot is running!"

@app.route('/logs', methods=['GET'])
def logs():
    return "<pre>" + "\n".join(log_buffer[-100:]) + "</pre>"

@app.route('/webhook', methods=['POST'])
def webhook():
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    try:
        data = request.get_json(force=True)
        log_buffer.append(f"[{timestamp}] ALERT RECEIVED: {data}")

        action = data.get("action")
        symbol = data.get("symbol")
        side = "Buy" if action == "buy" else "Sell"
        order_type = data.get("type", "market").capitalize()
        raw_qty = float(data.get("qty", 25))
        tp = float(data.get("tp")) if "tp" in data else None
        sl = float(data.get("sl")) if "sl" in data else None

        step = get_step_size(symbol)
        qty = round_qty_to_step(raw_qty, step)

        if action == "activate_trailing":
            ticker = session.get_tickers(category="linear", symbol=symbol)
            last_price = float(ticker["result"]["list"][0]["lastPrice"])
            position = session.get_positions(category="linear", symbol=symbol)
            side = "Buy" if float(position['result']['list'][0]['size']) < 0 else "Sell"
            thread = threading.Thread(target=monitor_price_and_set_trailing_stop, args=(symbol, last_price, side, qty))
            thread.start()
            return jsonify({"status": "trailing_started"}), 200

        order_response = session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        log_buffer.append(f"[{timestamp}] PRIMARY ORDER RESPONSE: {order_response}")

        if tp:
            tp_side = "Sell" if side == "Buy" else "Buy"
            tp_order = session.place_order(
                category="linear",
                symbol=symbol,
                side=tp_side,
                order_type="Limit",
                qty=qty,
                price=tp,
                time_in_force="PostOnly",
                reduce_only=True
            )
            log_buffer.append(f"[{timestamp}] TAKE PROFIT ORDER: {tp_order}")
        if sl:
            sl_side = "Sell" if side == "Buy" else "Buy"
            sl_order = session.place_order(
                category="linear",
                symbol=symbol,
                side=sl_side,
                order_type="Market",
                qty=qty,
                stop_loss=sl,
                time_in_force="GoodTillCancel",
                reduce_only=True
            )
            log_buffer.append(f"[{timestamp}] STOP LOSS ORDER: {sl_order}")

        ticker = session.get_tickers(category="linear", symbol=symbol)
        entry_price = float(ticker["result"]["list"][0]["lastPrice"])
        thread = threading.Thread(target=monitor_price_and_set_trailing_stop, args=(symbol, entry_price, side, qty))
        thread.start()

        return jsonify({"status": "ok", "order": order_response}), 200

    except Exception as e:
        log_buffer.append(f"[{timestamp}] ERROR: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 400
