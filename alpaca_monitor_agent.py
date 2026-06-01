import requests
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8957492846:AAGophSxXOSZGT4Gd1cLTNOICzxpZIH5wEU")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6518133529")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://trading-webhook-zhra.onrender.com")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}")

def run_monitor():
    """Agente Monitor: obtiene estado del bot via webhook"""
    try:
        import time
        response = None
        for intento in range(3):
            response = requests.get(f"{WEBHOOK_URL}/", timeout=15)
            if response.status_code != 429:
                break
            time.sleep(5)

        if response is None or response.status_code != 200:
            raise Exception(f"Webhook error: {response.status_code if response else 'sin respuesta'}")

        data = response.json()
        balance    = data.get("balance", 0)
        posiciones = data.get("posiciones", {})
        sl_pct     = data.get("stop_loss_pct", 1.0)
        tp_pct     = data.get("take_profit_pct", 2.0)
        ts_pct     = data.get("trailing_stop_pct", 0.5)

        report = f"[MONITOR ALPACA] {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        report += f"Balance: ${balance:,.2f}\n"
        report += f"Stop Loss: {sl_pct}% | Take Profit: {tp_pct}% | Trailing: {ts_pct}%\n\n"

        if posiciones:
            report += "Posiciones abiertas:\n"
            for sym, qty in posiciones.items():
                report += f"  {sym}: {qty} acciones\n"
        else:
            report += "Sin posiciones abiertas\n"

        send_telegram(report)
        return {
            "balance": balance,
            "posiciones": posiciones,
            "stop_loss_pct": sl_pct,
            "take_profit_pct": tp_pct,
            "trailing_stop_pct": ts_pct,
            "status": "ok"
        }
    except Exception as e:
        error_msg = f"[MONITOR ALPACA] Error: {str(e)}"
        send_telegram(error_msg)
        return {"error": str(e)}
