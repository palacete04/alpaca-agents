from flask import Flask, request, jsonify
import os
import threading
import time
from datetime import datetime
from alpaca_monitor_agent import run_monitor
from alpaca_analyst_agent import run_analysis_alpaca
from alpaca_optimizer_agent import run_optimization_alpaca
from alpaca_verifier_agent import run_verification_alpaca
import requests

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8957492846:AAGophSxXOSZGT4Gd1cLTNOICzxpZIH5wEU")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-5246245037")

ALPACA_PARAMS = {
    "stop_loss_pct": float(os.environ.get("STOP_LOSS_PCT", "1.0")),
    "take_profit_pct": float(os.environ.get("TAKE_PROFIT_PCT", "2.0")),
    "trailing_stop_pct": float(os.environ.get("TRAILING_STOP_PCT", "0.5")),
    "pct_capital": float(os.environ.get("PCT_CAPITAL", "20")),
    "simbolos": ["SPY", "QQQ", "IWM"],
    "timeframe": "5min",
    "estrategia": "MA Crossover 50/200"
}

alpaca_trades = []

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}")

def es_dia_habil():
    """Verifica si hoy es dia de mercado (lunes a viernes)"""
    return datetime.utcnow().weekday() < 5

def hora_utc():
    now = datetime.utcnow()
    return now.hour, now.minute

def scheduler():
    """Scheduler que manda reportes automaticos en horarios clave"""
    print("Scheduler iniciado")
    while True:
        try:
            if es_dia_habil():
                h, m = hora_utc()

                # 13:30 UTC = 10:30 Argentina = Apertura mercado
                if h == 13 and m == 30:
                    send_telegram("🔔 Mercado abriendo — SPY, QQQ, IWM")
                    run_analysis_alpaca()
                    run_monitor()
                    time.sleep(70)

                # 16:00 UTC = 13:00 Argentina = Reporte mediodia
                elif h == 16 and m == 0:
                    run_monitor()
                    time.sleep(70)

                # 20:00 UTC = 17:00 Argentina = Cierre mercado
                elif h == 20 and m == 0:
                    send_telegram("🔔 Mercado cerrando — Reporte del dia:")
                    run_monitor()
                    time.sleep(70)

                else:
                    time.sleep(30)
            else:
                time.sleep(300)

        except Exception as e:
            print(f"Error scheduler: {e}")
            time.sleep(60)

# Iniciar scheduler en background
scheduler_thread = threading.Thread(target=scheduler, daemon=True)
scheduler_thread.start()

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "Alpaca Multi-Agente activo",
        "agentes": ["/monitor", "/analyze", "/params", "/optimize", "/verify"],
        "simbolos": ["SPY", "QQQ", "IWM"],
        "scheduler": "activo — reportes a las 10:30, 13:00 y 17:00 Argentina"
    })

@app.route("/monitor", methods=["GET"])
def monitor():
    result = run_monitor()
    return jsonify(result)

@app.route("/analyze", methods=["GET"])
def analyze():
    result = run_analysis_alpaca()
    return jsonify(result)

@app.route("/params", methods=["GET"])
def params():
    return jsonify(ALPACA_PARAMS)

@app.route("/optimize", methods=["GET"])
def optimize():
    if len(alpaca_trades) < 5:
        return jsonify({"message": "Necesitas al menos 5 operaciones para optimizar"})
    result = run_optimization_alpaca(alpaca_trades, ALPACA_PARAMS)
    return jsonify(result)

@app.route("/verify", methods=["GET"])
def verify():
    result = run_verification_alpaca(ALPACA_PARAMS)
    return jsonify(result)

@app.route("/trade", methods=["POST"])
def register_trade():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Sin datos"}), 400
    trade = {
        "time": data.get("time", datetime.now().strftime("%Y-%m-%d %H:%M")),
        "symbol": data.get("symbol", ""),
        "side": data.get("side", ""),
        "qty": float(data.get("qty", 0)),
        "price": float(data.get("price", 0)),
        "profit": float(data.get("profit", 0)),
    }
    alpaca_trades.append(trade)
    return jsonify({"status": "ok", "total": len(alpaca_trades)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
