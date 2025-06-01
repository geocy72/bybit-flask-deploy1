from flask import Flask, request, jsonify
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
import threading
import time
import math
import os

app = Flask(__name__)

# === API KEYS ===
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "ZRyWx3GREmB9LQET4u")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "FzvPkH7tPuyDDZs0c7AAAskl1srtTvD4l8In")

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

TRAILING_PERCENT = 2.0
TRIGGER_PERCENT = 1.0
log_buffer = []
recent_signals = {}  # Dictionary για αποτροπή διπλών σημάτων
SIGNAL_TIMEOUT = 60  # Δευτερόλεπτα πριν θεωρηθεί "παλιό" σήμα

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

@app.route('/clear-logs', methods=['GET'])
def clear_logs():
    log_buffer.clear()
    return "🧹 Logs cleared successfully!"

@app.route('/webhook', methods=['POST'])
def webhook():
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    try:
        data = request.get_json(force=True)
        log_buffer.append(f"[{timestamp}] ALERT RECEIVED: {data}")

        # Δημιουργία μοναδικού κλειδιού για το σήμα
        signal_key = f"{data.get('symbol')}_{data.get('action')}_{data.get('qty')}"
        current_time = datetime.utcnow()

        # Έλεγχος αν το σήμα είναι πρόσφατο
        if signal_key in recent_signals and (current_time - recent_signals[signal_key]) < timedelta(seconds=SIGNAL_TIMEOUT):
            log_buffer.append(f"[{timestamp}] DUPLICATE SIGNAL IGNORED: {data}")
            return jsonify({"status": "ignored", "message": "Duplicate signal"}), 200

        # Ενημέρωση του τελευταίου σήματος
        recent_signals[signal_key] = current_time

        action = data.get("action")
        symbol = data.get("symbol")
        side = "Buy" if action == "buy" else "Sell"
        order_type = data.get("type", "market").capitalize()
        raw_qty = float(data.get("qty", 25))

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

        tp = float(data.get("tp")) if data.get("tp") else None
        sl = float(data.get("sl")) if data.get("sl") else None

        # Κύρια εντολή (Market)
        order_response = session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market" if order_type == "Market" else "Limit",
            qty=qty,
            time_in_force="GoodTillCancel" if order_type == "Limit" else None
        )
        log_buffer.append(f"[{timestamp}] PRIMARY ORDER RESPONSE: {order_response}")

        # Take Profit (Limit Order)
        if tp:
            tp_order = session.place_order(
                category="linear",
                symbol=symbol,
                side="Sell" if side == "Buy" else "Buy",  # Αντίθετη πλευρά
                order_type="Limit",
                qty=qty,
                price=str(tp)
            )
            log_buffer.append(f"[{timestamp}] TAKE PROFIT ORDER: {tp_order}")

        # Stop Loss (StopMarket Order)
        if sl:
            sl_order = session.place_order(
                category="linear",
                symbol=symbol,
                side="Sell" if side == "Buy" else "Buy",  # Αντίθετη πλευρά
                order_type="StopMarket",
                qty=qty,
                trigger_price=str(sl),
                trigger_by="LastPrice",
                triggerDirection=2 if side == "Buy" else 1,  # 2: κάτω για Buy, 1: πάνω για Sell
            )
            log_buffer.append(f"[{timestamp}] STOP LOSS ORDER: {sl_order}")

        return jsonify({"status": "ok", "order": order_response}), 200

    except Exception as e:
        log_buffer.append(f"[{timestamp}] ERROR: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
