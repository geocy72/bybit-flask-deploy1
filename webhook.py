from flask import Flask, request, jsonify
import requests
import json
import logging

app = Flask(__name__)

# === SETTINGS ===
API_KEY = "ZRyWx3GREmB9LQET4u"
API_SECRET = "FzvPkH7tPuyDDZs0c7AAAskl1srtTvD4l8In"
BASE_URL = "https://api.bybit.com"  # live
SYMBOL = "SUIUSDT"
QTY = 40
TP_MULT = 1.05
SL_MULT = 0.98
TRAILING_PERCENT = 2
TRAILING_TRIGGER = 1

# === LOGGING ===
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

# === ROUTES ===
@app.route("/", methods=["GET"])
def home():
    return "Bot is running."

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        logging.info(f"ALERT RECEIVED: {data}")
        action = data.get("action")

        # Get current price (mocked here — replace with real API call if needed)
        current_price = get_price(SYMBOL)

        if action == "buy":
            return place_market_order("Buy", SYMBOL, QTY, current_price)
        elif action == "sell":
            return place_market_order("Sell", SYMBOL, QTY, current_price)
        elif action == "cancel_all":
            return cancel_all_orders(SYMBOL)
        elif action == "activate_trailing":
            return place_trailing_stop(SYMBOL, QTY, current_price)
        else:
            return "Unknown action", 400

    except Exception as e:
        logging.error(f"ERROR: {e}")
        return "Internal Server Error", 500

# === PLACE ORDER ===
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

    logging.info(f"PRIMARY ORDER PAYLOAD: {payload}")
    response = requests.post(endpoint, headers=headers, data=json.dumps(payload))
    logging.info(f"PRIMARY ORDER RESPONSE: {response.json()}")
    return jsonify(response.json())

# === CANCEL ===
def cancel_all_orders(symbol):
    endpoint = f"{BASE_URL}/v5/order/cancel-all"
    payload = {"category": "linear", "symbol": symbol}
    headers = {
        "X-BYBIT-API-KEY": API_KEY,
        "Content-Type": "application/json"
    }
    response = requests.post(endpoint, headers=headers, data=json.dumps(payload))
    logging.info(f"CANCEL RESPONSE: {response.json()}")
    return jsonify(response.json())

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
    headers = {
        "X-BYBIT-API-KEY": API_KEY,
        "Content-Type": "application/json"
    }
    logging.info(f"TRAILING ORDER PAYLOAD: {payload}")
    response = requests.post(endpoint, headers=headers, data=json.dumps(payload))
    logging.info(f"TRAILING ORDER RESPONSE: {response.json()}")
    return jsonify(response.json())

# === MOCK PRICE ===
def get_price(symbol):
    # Replace this with real Bybit ticker fetch if needed
    return 4.5

if __name__ == "__main__":
    app.run(debug=True)
