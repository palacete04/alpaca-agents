"""
ALPACA MULTI-AGENTE + WEBHOOK
v2: Webhook TradingView integrado + protecciones + Telegram completo
- Max 1 simbolo abierto a la vez
- Qty calculada sobre equity (consistente)
- Notificaciones Telegram en cada operacion
- Monitor, Analista, Optimizador, Verificador
- Scheduler automatico
"""

from flask import Flask, request, jsonify
import os
import threading
import time
import requests
import alpaca_trade_api as tradeapi
from datetime import datetime

# ─────────────────────────────────────────
# IMPORTS DE AGENTES
# ─────────────────────────────────────────
try:
    from alpaca_monitor_agent import run_monitor
    from alpaca_analyst_agent import run_analysis_alpaca
    from alpaca_optimizer_agent import run_optimization_alpaca
    from alpaca_verifier_agent import run_verification_alpaca
    from alpaca_scheduler import start_scheduler_alpaca
    print("Imports exitosos")
except Exception as e:
    print(f"Error de import: {e}")
    raise

# ─────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────
API_KEY           = os.environ.get("API_KEY")
API_SECRET        = os.environ.get("API_SECRET")
ALPACA_BASE_URL   = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
TOKEN             = os.environ.get("TOKEN", "MI_TOKEN_SECRETO")
PCT_CAPITAL       = float(os.environ.get("PCT_CAPITAL", "20"))
STOP_LOSS_PCT     = float(os.environ.get("STOP_LOSS_PCT", "1.0"))
TAKE_PROFIT_PCT   = float(os.environ.get("TAKE_PROFIT_PCT", "2.0"))
TRAILING_STOP_PCT = float(os.environ.get("TRAILING_STOP_PCT", "0.5"))
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "8957492846:AAGophSxXOSZGT4Gd1cLTNOICzxpZIH5wEU")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "-5246245037")

SIMBOLOS = ["SPY", "QQQ", "IWM"]

ALPACA_PARAMS = {
    "stop_loss_pct":     STOP_LOSS_PCT,
    "take_profit_pct":   TAKE_PROFIT_PCT,
    "trailing_stop_pct": TRAILING_STOP_PCT,
    "pct_capital":       PCT_CAPITAL,
    "simbolos":          SIMBOLOS,
    "timeframe":         "5min",
    "estrategia":        "MA Crossover 50/200"
}

api = tradeapi.REST(API_KEY, API_SECRET, ALPACA_BASE_URL, api_version='v2')
app = Flask(__name__)

# Estado en memoria
alpaca_trades = []
max_prices    = {}   # precio maximo alcanzado por simbolo (trailing)
qty_abierta   = {}   # qty guardada al abrir para cierre consistente

# ─────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}")

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

# ─────────────────────────────────────────
# HELPERS ALPACA
# ─────────────────────────────────────────
def tengo_posicion_symbol(symbol):
    try:
        pos = api.get_position(symbol)
        return int(float(pos.qty))
    except:
        return 0

def hay_posicion_abierta_cualquier_simbolo():
    """Retorna (True, simbolo) si hay cualquier posicion abierta"""
    for sym in SIMBOLOS:
        qty = tengo_posicion_symbol(sym)
        if qty > 0:
            return True, sym
    return False, None

def hay_orden_abierta(symbol):
    try:
        ordenes = api.list_orders(status='open')
        return any(o.symbol == symbol for o in ordenes)
    except:
        return False

def puede_comprar(symbol):
    if tengo_posicion_symbol(symbol) > 0:
        log(f"Ya tengo posicion en {symbol}")
        return False, f"Ya hay posicion en {symbol}"
    hay_pos, sym_abierto = hay_posicion_abierta_cualquier_simbolo()
    if hay_pos:
        log(f"Ya tengo posicion en {sym_abierto}, no compro {symbol}")
        return False, f"Posicion abierta en {sym_abierto}"
    if hay_orden_abierta(symbol):
        log(f"Orden pendiente para {symbol}")
        return False, f"Orden pendiente en {symbol}"
    return True, ""

def puede_vender(symbol):
    if tengo_posicion_symbol(symbol) == 0:
        return False, "Sin posicion"
    if hay_orden_abierta(symbol):
        return False, "Orden pendiente"
    return True, ""

def calcular_qty(symbol):
    """Qty basada en equity total — consistente siempre"""
    cuenta  = api.get_account()
    capital = float(cuenta.equity)
    precio  = float(api.get_latest_trade(symbol).price)
    qty     = int((capital * PCT_CAPITAL / 100) / precio)
    return max(qty, 1)

def precio_actual(symbol):
    try:
        return float(api.get_latest_trade(symbol).price)
    except:
        return 0

def mercado_alcista(symbol):
    try:
        barras = api.get_bars(symbol, tradeapi.TimeFrame.Day, limit=200).df
        if len(barras) < 200:
            return True
        ema50  = barras['close'].ewm(span=50).mean().iloc[-1]
        ema200 = barras['close'].ewm(span=200).mean().iloc[-1]
        return ema50 > ema200
    except:
        return True

def registrar_trade(symbol, side, qty, precio_entrada, precio_salida=None, motivo=""):
    """Registra operacion en memoria y calcula resultado"""
    profit = 0
    if precio_salida and precio_salida > 0:
        if side == "buy":
            profit = round((precio_salida - precio_entrada) * qty, 2)
        else:
            profit = round((precio_entrada - precio_salida) * qty, 2)

    trade = {
        "time":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "symbol":  symbol,
        "side":    side,
        "qty":     qty,
        "price":   precio_entrada,
        "exit":    precio_salida,
        "profit":  profit,
        "motivo":  motivo,
    }
    alpaca_trades.append(trade)
    return profit

# ─────────────────────────────────────────
# MONITOR DE STOPS (thread en background)
# ─────────────────────────────────────────
def verificar_stops(symbol):
    try:
        pos = api.get_position(symbol)
        qty = int(float(pos.qty))
        if qty == 0 or hay_orden_abierta(symbol):
            return

        precio_entrada = float(pos.avg_entry_price)
        precio_now     = precio_actual(symbol)
        if precio_now == 0:
            return

        # Actualizar maximo para trailing
        if symbol not in max_prices or precio_now > max_prices[symbol]:
            max_prices[symbol] = precio_now

        # Take Profit
        tp_precio = precio_entrada * (1 + TAKE_PROFIT_PCT / 100)
        if precio_now >= tp_precio:
            ganancia = round((precio_now - precio_entrada) * qty, 2)
            api.submit_order(symbol=symbol, qty=qty, side="sell", type="market", time_in_force="day")
            registrar_trade(symbol, "sell", qty, precio_entrada, precio_now, "take_profit")
            send_telegram(
                f"✅ TAKE PROFIT {symbol}\n"
                f"Entrada: ${precio_entrada:.2f} → Salida: ${precio_now:.2f}\n"
                f"Ganancia: ${ganancia:.2f}"
            )
            max_prices.pop(symbol, None)
            qty_abierta.pop(symbol, None)
            log(f"TAKE PROFIT {symbol} +${ganancia:.2f}")
            return

        # Stop Loss
        sl_precio = precio_entrada * (1 - STOP_LOSS_PCT / 100)
        if precio_now <= sl_precio:
            perdida = round((precio_now - precio_entrada) * qty, 2)
            api.submit_order(symbol=symbol, qty=qty, side="sell", type="market", time_in_force="day")
            registrar_trade(symbol, "sell", qty, precio_entrada, precio_now, "stop_loss")
            send_telegram(
                f"❌ STOP LOSS {symbol}\n"
                f"Entrada: ${precio_entrada:.2f} → Salida: ${precio_now:.2f}\n"
                f"Perdida: ${perdida:.2f}"
            )
            max_prices.pop(symbol, None)
            qty_abierta.pop(symbol, None)
            log(f"STOP LOSS {symbol} ${perdida:.2f}")
            return

        # Trailing Stop
        trailing_precio = max_prices[symbol] * (1 - TRAILING_STOP_PCT / 100)
        if precio_now <= trailing_precio:
            resultado = round((precio_now - precio_entrada) * qty, 2)
            api.submit_order(symbol=symbol, qty=qty, side="sell", type="market", time_in_force="day")
            registrar_trade(symbol, "sell", qty, precio_entrada, precio_now, "trailing_stop")
            emoji = "✅" if resultado >= 0 else "❌"
            send_telegram(
                f"{emoji} TRAILING STOP {symbol}\n"
                f"Entrada: ${precio_entrada:.2f} → Salida: ${precio_now:.2f}\n"
                f"Resultado: ${resultado:+.2f}"
            )
            max_prices.pop(symbol, None)
            qty_abierta.pop(symbol, None)
            log(f"TRAILING STOP {symbol} ${resultado:+.2f}")

    except Exception as e:
        log(f"Error stops {symbol}: {e}")

def monitor_stops_loop():
    while True:
        try:
            clock = api.get_clock()
            if clock.is_open:
                for sym in SIMBOLOS:
                    if tengo_posicion_symbol(sym) > 0:
                        verificar_stops(sym)
        except:
            pass
        time.sleep(60)

# ─────────────────────────────────────────
# MONITOR DE ALERTAS (cada 5 operaciones)
# ─────────────────────────────────────────
def analizar_trades():
    if len(alpaca_trades) < 3:
        return
    total  = len(alpaca_trades)
    wins   = sum(1 for t in alpaca_trades if t.get("profit", 0) > 0)
    losses = total - wins
    pnl    = round(sum(t.get("profit", 0) for t in alpaca_trades), 2)
    wr     = round(wins / total * 100, 1) if total > 0 else 0

    alertas = []

    if total >= 5 and wr < 40:
        alertas.append(f"[ALERTA] Win rate bajo: {wr}% ({wins}/{total})")
    if pnl < -200:
        alertas.append(f"[ALERTA] Perdida acumulada: ${pnl}")

    # Perdidas consecutivas por simbolo
    perdidas_consec = {}
    for t in alpaca_trades:
        sym = t.get("symbol", "")
        if t.get("profit", 0) < 0:
            perdidas_consec[sym] = perdidas_consec.get(sym, 0) + 1
        else:
            perdidas_consec[sym] = 0
    for sym, consec in perdidas_consec.items():
        if consec >= 3:
            alertas.append(f"[ALERTA] {sym}: 3 perdidas consecutivas")

    for a in alertas:
        send_telegram(a)

    # Reporte cada 5 operaciones
    if total % 5 == 0:
        by_sym = {}
        for t in alpaca_trades:
            sym = t.get("symbol", "?")
            if sym not in by_sym:
                by_sym[sym] = {"wins": 0, "losses": 0, "profit": 0}
            if t.get("profit", 0) > 0:
                by_sym[sym]["wins"] += 1
            else:
                by_sym[sym]["losses"] += 1
            by_sym[sym]["profit"] = round(by_sym[sym]["profit"] + t.get("profit", 0), 2)

        reporte = f"[REPORTE ALPACA] {total} operaciones\n"
        reporte += f"Win rate: {wr}% | P&L: ${pnl}\n"
        for sym, st in by_sym.items():
            reporte += f"{sym}: {st['wins']}G/{st['losses']}P (${st['profit']})\n"
        send_telegram(reporte)

# ─────────────────────────────────────────
# INICIAR THREADS
# ─────────────────────────────────────────
threading.Thread(target=monitor_stops_loop, daemon=True).start()
start_scheduler_alpaca(lambda: alpaca_trades)

# Mensaje de inicio
send_telegram(
    f"🚀 Alpaca Bot iniciado\n"
    f"SL: {STOP_LOSS_PCT}% | TP: {TAKE_PROFIT_PCT}% | TS: {TRAILING_STOP_PCT}%\n"
    f"Capital por op: {PCT_CAPITAL}% | Simbolos: {', '.join(SIMBOLOS)}"
)

# ─────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────

@app.route("/", methods=["GET"])
def home():
    try:
        cuenta = api.get_account()
        posiciones = {}
        for sym in SIMBOLOS:
            qty = tengo_posicion_symbol(sym)
            if qty > 0:
                posiciones[sym] = qty
        return jsonify({
            "status":           "Alpaca Bot activo",
            "balance":          float(cuenta.cash),
            "equity":           float(cuenta.equity),
            "posiciones":       posiciones,
            "stop_loss_pct":    STOP_LOSS_PCT,
            "take_profit_pct":  TAKE_PROFIT_PCT,
            "trailing_stop_pct":TRAILING_STOP_PCT,
            "pct_capital":      PCT_CAPITAL,
            "agentes":          ["/monitor", "/analyze", "/params", "/optimize", "/verify"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/webhook", methods=["POST"])
def webhook():
    """Recibe señales de TradingView y ejecuta ordenes en Alpaca"""
    data = request.get_json()

    if not data or data.get("token") != TOKEN:
        log("Token invalido")
        return jsonify({"error": "No autorizado"}), 403

    accion = data.get("accion", "").upper()
    symbol = data.get("symbol", "SPY").upper()
    log(f"Señal recibida: {accion} {symbol}")

    try:
        if accion == "COMPRAR":
            ok, razon = puede_comprar(symbol)
            if not ok:
                log(f"Compra bloqueada: {razon}")
                return jsonify({"status": f"Bloqueada — {razon}"}), 200

            if not mercado_alcista(symbol):
                log(f"Mercado bajista {symbol}, compra bloqueada")
                return jsonify({"status": "Mercado bajista, compra bloqueada"}), 200

            qty    = calcular_qty(symbol)
            precio = precio_actual(symbol)

            api.submit_order(
                symbol=symbol, qty=qty,
                side="buy", type="market", time_in_force="day"
            )
            max_prices[symbol]  = precio
            qty_abierta[symbol] = qty
            registrar_trade(symbol, "buy", qty, precio)
            analizar_trades()

            send_telegram(
                f"📈 COMPRA {symbol}\n"
                f"Qty: {qty} acciones\n"
                f"Precio aprox: ${precio:.2f}\n"
                f"Capital usado: ~${qty * precio:,.0f} ({PCT_CAPITAL}%)\n"
                f"SL: ${precio * (1 - STOP_LOSS_PCT/100):.2f} | "
                f"TP: ${precio * (1 + TAKE_PROFIT_PCT/100):.2f}"
            )
            log(f"COMPRA ejecutada — {qty} x {symbol} @ ${precio:.2f}")
            return jsonify({"status": "Compra ejecutada", "qty": qty, "symbol": symbol}), 200

        elif accion == "VENDER":
            ok, razon = puede_vender(symbol)
            if not ok:
                log(f"Venta bloqueada: {razon}")
                return jsonify({"status": f"Bloqueada — {razon}"}), 200

            qty    = tengo_posicion_symbol(symbol)
            precio = precio_actual(symbol)

            try:
                pos            = api.get_position(symbol)
                precio_entrada = float(pos.avg_entry_price)
                resultado      = round((precio - precio_entrada) * qty, 2)
                resultado_str  = f"Resultado: ${resultado:+.2f}"
                emoji          = "✅" if resultado >= 0 else "❌"
            except:
                precio_entrada = 0
                resultado      = 0
                resultado_str  = ""
                emoji          = "📉"

            api.submit_order(
                symbol=symbol, qty=qty,
                side="sell", type="market", time_in_force="day"
            )
            registrar_trade(symbol, "sell", qty, precio_entrada, precio, "señal_tradingview")
            analizar_trades()
            max_prices.pop(symbol, None)
            qty_abierta.pop(symbol, None)

            send_telegram(
                f"{emoji} VENTA {symbol} (señal TradingView)\n"
                f"Qty: {qty} acciones\n"
                f"Precio aprox: ${precio:.2f}\n"
                f"{resultado_str}"
            )
            log(f"VENTA ejecutada — {qty} x {symbol} @ ${precio:.2f}")
            return jsonify({"status": "Venta ejecutada", "qty": qty, "symbol": symbol}), 200

        else:
            return jsonify({"status": "Accion no reconocida"}), 200

    except Exception as e:
        log(f"Error webhook: {e}")
        send_telegram(f"⚠️ Error en webhook {symbol}: {str(e)}")
        return jsonify({"error": str(e)}), 500

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
def register_trade_endpoint():
    """Endpoint para registrar trades manualmente"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Sin datos"}), 400
    trade = {
        "time":   data.get("time", datetime.now().strftime("%Y-%m-%d %H:%M")),
        "symbol": data.get("symbol", ""),
        "side":   data.get("side", ""),
        "qty":    float(data.get("qty", 0)),
        "price":  float(data.get("price", 0)),
        "profit": float(data.get("profit", 0)),
    }
    alpaca_trades.append(trade)
    return jsonify({"status": "ok", "total": len(alpaca_trades)})

@app.route("/stats", methods=["GET"])
def stats():
    """Ver estadisticas de operaciones"""
    if not alpaca_trades:
        return jsonify({"message": "Sin operaciones aun"})
    total  = len(alpaca_trades)
    wins   = sum(1 for t in alpaca_trades if t.get("profit", 0) > 0)
    pnl    = round(sum(t.get("profit", 0) for t in alpaca_trades), 2)
    wr     = round(wins / total * 100, 1) if total > 0 else 0
    by_sym = {}
    for t in alpaca_trades:
        sym = t.get("symbol", "?")
        if sym not in by_sym:
            by_sym[sym] = {"wins": 0, "losses": 0, "profit": 0}
        if t.get("profit", 0) > 0:
            by_sym[sym]["wins"] += 1
        else:
            by_sym[sym]["losses"] += 1
        by_sym[sym]["profit"] = round(by_sym[sym]["profit"] + t.get("profit", 0), 2)
    return jsonify({
        "total":         total,
        "wins":          wins,
        "losses":        total - wins,
        "win_rate":      wr,
        "pnl_total":     pnl,
        "por_simbolo":   by_sym,
    })

@app.route("/posiciones", methods=["GET"])
def posiciones():
    """Ver posiciones abiertas actuales en Alpaca"""
    try:
        result = {}
        for sym in SIMBOLOS:
            qty = tengo_posicion_symbol(sym)
            if qty > 0:
                pos = api.get_position(sym)
                result[sym] = {
                    "qty":           qty,
                    "precio_entrada": float(pos.avg_entry_price),
                    "precio_actual":  precio_actual(sym),
                    "pnl_no_realizado": float(pos.unrealized_pl),
                }
        return jsonify({"posiciones": result, "total": len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
