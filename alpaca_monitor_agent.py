import requests
import os
from datetime import datetime
import alpaca_trade_api as tradeapi

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8957492846:AAGophSxXOSZGT4Gd1cLTNOICzxpZIH5wEU")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6518133529")
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}")

def get_alpaca_client():
    return tradeapi.REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL, api_version='v2')

def run_monitor():
    """Agente Monitor: estado general del bot de Alpaca"""
    try:
        api = get_alpaca_client()
        cuenta = api.get_account()
        
        balance = float(cuenta.cash)
        equity = float(cuenta.equity)
        ganancia_dia = float(cuenta.equity) - float(cuenta.last_equity)
        
        # Posiciones abiertas
        posiciones = []
        simbolos = ["SPY", "QQQ", "IWM"]
        for sym in simbolos:
            try:
                pos = api.get_position(sym)
                qty = int(float(pos.qty))
                precio_entrada = float(pos.avg_entry_price)
                precio_actual = float(pos.current_price)
                pnl = float(pos.unrealized_pl)
                pnl_pct = float(pos.unrealized_plpc) * 100
                posiciones.append({
                    "symbol": sym,
                    "qty": qty,
                    "entrada": precio_entrada,
                    "actual": precio_actual,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct
                })
            except:
                pass
        
        # Ultimas 5 operaciones
        actividades = api.get_activities(activity_types='FILL')
        ultimas = list(actividades)[:5]
        
        # Armar reporte
        report = f"[MONITOR ALPACA] {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        report += f"Balance: ${balance:,.2f}\n"
        report += f"Equity: ${equity:,.2f}\n"
        report += f"Ganancia hoy: ${ganancia_dia:+.2f}\n\n"
        
        if posiciones:
            report += "Posiciones abiertas:\n"
            for p in posiciones:
                report += f"  {p['symbol']}: {p['qty']} acc @ ${p['entrada']:.2f} → ${p['actual']:.2f} ({p['pnl_pct']:+.2f}%)\n"
        else:
            report += "Sin posiciones abiertas\n"
        
        if ultimas:
            report += "\nUltimas operaciones:\n"
            for act in ultimas:
                side = "COMPRA" if act.side == "buy" else "VENTA"
                report += f"  {side} {act.qty} {act.symbol} @ ${float(act.price):.2f}\n"
        
        send_telegram(report)
        
        return {
            "balance": balance,
            "equity": equity,
            "ganancia_dia": ganancia_dia,
            "posiciones": posiciones,
            "status": "ok"
        }
        
    except Exception as e:
        error_msg = f"[MONITOR ALPACA] Error: {str(e)}"
        send_telegram(error_msg)
        return {"error": str(e)}
