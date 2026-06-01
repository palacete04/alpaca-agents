from flask import Flask, request, jsonify
import os
from datetime import datetime
try:
    from alpaca_monitor_agent import run_monitor
    from alpaca_analyst_agent import run_analysis_alpaca
    from alpaca_optimizer_agent import run_optimization_alpaca
    from alpaca_verifier_agent import run_verification_alpaca
    print("Imports exitosos")
except Exception as e:
    print(f"Error de import: {e}")
    raise

app = Flask(__name__)

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

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "Alpaca Multi-Agente activo",
        "agentes": ["/monitor", "/analyze", "/params", "/optimize", "/verify"],
        "simbolos": ["SPY", "QQQ", "IWM"]
    })

@app.route("/monitor", methods=["GET"])
def monitor():
    """Agente Monitor: estado general del bot"""
    result = run_monitor()
    return jsonify(result)

@app.route("/analyze", methods=["GET"])
def analyze():
    """Agente Analista: analiza mercado y sugiere estrategias"""
    result = run_analysis_alpaca()
    return jsonify(result)

@app.route("/params", methods=["GET"])
def params():
    """Ver parametros actuales del bot"""
    return jsonify(ALPACA_PARAMS)

@app.route("/optimize", methods=["GET"])
def optimize():
    """Agente Optimizador: sugiere ajustes a los parametros"""
    if len(alpaca_trades) < 5:
        return jsonify({"message": "Necesitas al menos 5 operaciones para optimizar"})
    result = run_optimization_alpaca(alpaca_trades, ALPACA_PARAMS)
    return jsonify(result)

@app.route("/verify", methods=["GET"])
def verify():
    """Agente Verificador: verifica parametros y estado del webhook"""
    result = run_verification_alpaca(ALPACA_PARAMS)
    return jsonify(result)

@app.route("/trade", methods=["POST"])
def register_trade():
    """Registra una operacion para el historial"""
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
