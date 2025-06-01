from flask import Flask, request, jsonify
import requests
import json
import logging
import os
import time
import hmac
import hashlib

app = Flask(__name__)

# === SETTINGS ===
API_KEY = "ZRyWx3GREmB9LQET4u"
API_SECRET = "FzvPkH7tPuyDDZs0c7AAAskl1srtTvD4l8In"
BASE_URL = "https://api.bybit.com"
QTY = 40
TP_MULT = 1.05
SL_MULT = 0.98
TRAILING_PERCENT = 2
TRAILING_TRIGGER = 1

# === LOGGING ===
LOG_FILENAME = "webhookbot.log"
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILENAME),
        logging.StreamHandler()
    ]
)

# === HMAC SIGNATURE ===
def generate_signature(api_key, api_secret, req_time, body=""):
    param_str = f"{api_key}{req_time}{body}"
    return hmac.new(bytes(api_secret, "utf-8"), bytes(param_str, "utf-8"), hashlib.sha256).hexdigest()

# === ROUTES ===
@app.route("/", methods=["GET"])
def home():
    return "Webhook bot is running."

@app.route("/logs", methods=["GET"])
def get_logs():
    try:
        if not os.path.exists(LOG_FILENAME):
            return "No log file found.", 404
        with open(LOG_FILENAME, "r") as f:
            return f"<pre>{f.read()}</pre>"
    except Exception as e:
        return f"Error: {e}", 500

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        logging.info(f"ALERT RECEIVED: {json.dumps(data)}")

        mode = data.get("mode", "order")
        if mode == "alert":
            logging.info("ALERT ONLY MODE – no order executed.")
            return jsonify({"status": "alert_received"}), 200

        action = data.get("action")
        symbol = data.get("symbol", "SUIUSDT")
        qty = data.get("qty", QTY)
        current_price = get_price(symbol)

        logging.info(f"Current price for {symbol}: {current_price}")

        if action == "buy":
            return place_market_order("Buy", symbol, qty, current_price)
        elif action == "sell":
            return place_market_order("Sell", symbol, qty, current_price)
        elif action == "cancel_all":
            return cancel_all_orders(symbol)
        elif action == "activate_trailing":
            return place_trailing_stop(symbol, qty, current_price)
        else:
            logging.warning(f"Unknown action: {action}")
            return "Unknown action", 400

    except Exception as e:
        logging.error(f"ERROR in /webhook: {str(e)}")
        return "Internal Server Error", 500

# === MARKET ORDER ===
def place_market_order(side, symbol, qty, price):
    endpoint = f"{BASE_URL}/v5/order/create"
    tp = price * TP_MULT if side == "Buy" else price * SL_MULT
    sl = price * SL_MULT if side == "Buy" else price * TP_MULT

    payload = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "order_type": "Market",
        "qty": str(qty),
        "take_profit": f"{tp:.4f}",
        "stop_loss": f"{sl:.4f}",
        "time_in_force": "GoodTillCancel"
    }

    body = json.dumps(payload)
    req_time = str(int(time.time() * 1000))
    signature = generate_signature(API_KEY, API_SECRET, req_time, body)

    headers = {
        "X-BYBIT-API-KEY": API_KEY,
        "X-BYBIT-TIMESTAMP": req_time,
        "X-BYBIT-SIGN": signature,
        "Content-Type": "application/json"
    }

    try:
        logging.info(f"[{side.upper()} ORDER] Payload: {payload}")
        response = requests.post(endpoint, headers=headers, data=body)
        logging.info(f"[{side.upper()} ORDER] Response: {response.text}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logging.error(f"Exception placing {side} order: {e}")
        return jsonify({"error": str(e)}), 500

# === CANCEL ALL ===
def cancel_all_orders(symbol):
    endpoint = f"{BASE_URL}/v5/order/cancel-all"
    payload = {"category": "linear", "symbol": symbol}
    body = json.dumps(payload)
    req_time = str(int(time.time() * 1000))
    signature = generate_signature(API_KEY, API_SECRET, req_time, body)

    headers = {
        "X-BYBIT-API-KEY": API_KEY,
        "X-BYBIT-TIMESTAMP": req_time,
        "X-BYBIT-SIGN": signature,
        "Content-Type": "application/json"
    }

    try:
        logging.info("[CANCEL ALL] Sending request")
        response = requests.post(endpoint, headers=headers, data=body)
        logging.info(f"[CANCEL ALL] Response: {response.text}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logging.error(f"Exception canceling orders: {e}")
        return jsonify({"error": str(e)}), 500

# === TRAILING STOP ===
def place_trailing_stop(symbol, qty, entry_price):
    trigger_price = entry_price * (1 + TRAILING_TRIGGER / 100)
    endpoint = f"{BASE_URL}/v5/order/create"
    payload = {
        "category": "linear",
        "symbol": symbol,
        "side": "Sell",
        "order_type": "Market",
        "qty": str(qty),
        "triggerDirection": 1,
        "triggerPrice": f"{trigger_price:.4f}",
        "orderFilter": "Order",
        "tpslMode": "Partial",
        "trailValue": str(TRAILING_PERCENT),
        "trailType": "percentage"
    }

    body = json.dumps(payload)
    req_time = str(int(time.time() * 1000))
    signature = generate_signature(API_KEY, API_SECRET, req_time, body)

    headers = {
        "X-BYBIT-API-KEY": API_KEY,
        "X-BYBIT-TIMESTAMP": req_time,
        "X-BYBIT-SIGN": signature,
        "Content-Type": "application/json"
    }

    try:
        logging.info("[TRAILING STOP] Sending request")
        logging.info(f"[TRAILING STOP] Payload: {payload}")
        response = requests.post(endpoint, headers=headers, data=body)
        logging.info(f"[TRAILING STOP] Response: {response.text}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logging.error(f"Exception placing trailing stop: {e}")
        return jsonify({"error": str(e)}), 500

# === PRICE MOCK ===
def get_price(symbol):
    return 4.5  # Replace with real fetch later

if __name__ == "__main__":
    app.run(debug=True)
