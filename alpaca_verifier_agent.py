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

def verify_alpaca_params(params):
    issues = []
    sl  = params.get('stop_loss_pct', 1.0)
    tp  = params.get('take_profit_pct', 2.0)
    ts  = params.get('trailing_stop_pct', 0.5)
    pct = params.get('pct_capital', 20)
    if sl > 3:
        issues.append(f"Stop Loss muy alto ({sl}%) - maximo 3%")
    if tp < sl * 2:
        issues.append(f"Take Profit ({tp}%) debe ser al menos el doble del SL ({sl}%)")
    if ts > sl:
        issues.append(f"Trailing Stop ({ts}%) no puede ser mayor al SL ({sl}%)")
    if pct > 30:
        issues.append(f"Capital por operacion muy alto ({pct}%) - maximo 30%")
    if pct < 5:
        issues.append(f"Capital por operacion muy bajo ({pct}%) - minimo 5%")
    return len(issues) == 0, issues

def verify_webhook(webhook_url):
    try:
        response = requests.get(webhook_url, timeout=10)
        if response.status_code == 200:
            return True, response.json()
        return False, f"Status: {response.status_code}"
    except Exception as e:
        return False, str(e)

def run_verification_alpaca(params):
    params_ok, issues = verify_alpaca_params(params)
    webhook_ok, webhook_data = verify_webhook(WEBHOOK_URL)

    report = f"[VERIFICADOR ALPACA] {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
    report += f"Parametros: {'OK' if params_ok else 'PROBLEMAS'}\n"
    if issues:
        for issue in issues:
            report += f"  - {issue}\n"
    else:
        report += f"  SL: {params.get('stop_loss_pct')}% | TP: {params.get('take_profit_pct')}% | Capital: {params.get('pct_capital')}%\n"

    report += f"\nWebhook: {'OK' if webhook_ok else 'ERROR'}\n"
    if webhook_ok and isinstance(webhook_data, dict):
        report += f"  Balance: ${webhook_data.get('balance', 0):,.2f}\n"
        posiciones = webhook_data.get('posiciones', {})
        report += f"  Posiciones: {posiciones if posiciones else 'Ninguna'}\n"
    else:
        report += f"  Error: {webhook_data}\n"

    send_telegram(report)
    return {
        "params_ok": params_ok,
        "issues": issues,
        "webhook_ok": webhook_ok,
        "webhook_data": webhook_data if isinstance(webhook_data, dict) else str(webhook_data)
    }
