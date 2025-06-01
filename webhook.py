from flask import Flask, request, jsonify
import requests
import json
import logging

app = Flask(__name__)

# === SETTINGS ===
API_KEY = "ZRyWx3GREmB9LQET4u"
API_SECRET = "FzvPkH7tPuyDDZs0c7AAAskl1srtTvD4l8In"
BASE_URL = "https://api.bybit.com"
SYMBOL = "SUIUSDT"
QTY = 40
TP_MULT = 1.05
SL_MULT = 0.98
TRAILING_PERCENT = 2
TRAILING_TRIGGER = 1

# === LOGGING ===
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

# === ROUTES ===
@app.route("/", methods=["GET"])
def home():
    return "Bot is running."

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        logging.info(f"ALERT RECEIVED: {json.dumps(data)}")
        action = data.get("action")

        current_price = get_price(SYMBOL)
        logging.info(f"Current price for {SYMBOL}: {current_price}")

        if action == "buy":
            return place_market_order("Buy", SYMBOL, QTY, current_price)
        elif action == "sell":
            return place_market_order("Sell", SYMBOL, QTY, current_price)
        elif action == "cancel_all":
            return cancel_all_orders(SYMBOL)
        elif action == "activate_trailing":
            return place_trailing_stop(SYMBOL, QTY, current_price)
        else:
            logging.warning(f"Unknown action: {action}")
            return "Unknown action", 400

    except Exception as e:
        logging.error(f"ERROR in /webhook: {str(e)}")
        return "Internal Server Error", 500

# === PLACE MARKET ORDER ===
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

    headers = {
        "X-BYBIT-API-KEY": API_KEY,
        "Content-Type": "application/json"
    }

    try:
        logging.info(f"[{side.upper()} ORDER] Payload: {payload}")
        response = requests.post(endpoint, headers=headers, data=json.dumps(payload))
        logging.info(f"[{side.upper()} ORDER] Status: {response.status_code}")
        logging.info(f"[{side.upper()} ORDER] Response: {response.text}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logging.error(f"Exception while placing {side} order: {e}")
        return jsonify({"error": str(e)}), 500

# === CANCEL ALL ORDERS ===
def cancel_all_orders(symbol):
    endpoint = f"{BASE_URL}/v5/order/cancel-all"
    payload = {"category": "linear", "symbol": symbol}
    headers = {
        "X-BYBIT-API-KEY": API_KEY,
        "Content-Type": "application/json"
    }

    try:
        logging.info(f"[CANCEL ALL] Payload: {payload}")
        response = requests.post(endpoint, headers=headers, data=json.dumps(payload))
        logging.info(f"[CANCEL ALL] Status: {response.status_code}")
        logging.info(f"[CANCEL ALL] Response: {response.text}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logging.error(f"Exception while canceling orders: {e}")
        return jsonify({"error": str(e)}), 500

# === TRAILING STOP ORDER ===
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

    headers = {
        "X-BYBIT-API-KEY": API_KEY,
        "Content-Type": "application/json"
    }

    try:
        logging.info(f"[TRAILING STOP] Payload: {payload}")
        response = requests.post(endpoint, headers=headers, data=json.dumps(payload))
        logging.info(f"[TRAILING STOP] Status: {response.status_code}")
        logging.info(f"[TRAILING STOP] Response: {response.text}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logging.error(f"Exception while placing trailing stop: {e}")
        return jsonify({"error": str(e)}), 500

# === GET MOCK PRICE ===
def get_price(symbol):
    # FIXME: Replace with real ticker fetch via Bybit /v5/market/tickers if needed
    return 4.5

# === RUN ===
if __name__ == "__main__":
    app.run(debug=True)
