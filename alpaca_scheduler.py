import threading
import time
import requests
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8957492846:AAGophSxXOSZGT4Gd1cLTNOICzxpZIH5wEU")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-5246245037")  # Grupo Bot Alpaca
BASE_URL = os.environ.get("BASE_URL", "https://alpaca-agents.onrender.com")
# WEBHOOK_URL ahora es el mismo servidor (webhook integrado en app_alpaca.py)
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://alpaca-agents.onrender.com")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}")

def check_webhook():
    """Verifica si el bot de Alpaca está activo"""
    try:
        response = requests.get(f"{WEBHOOK_URL}/", timeout=10)
        if response.status_code == 200:
            data = response.json()
            return True, data.get("balance", 0)
        return False, 0
    except Exception as e:
        print(f"Error webhook check: {e}")
        return False, 0

def run_agent_pipeline_alpaca(alpaca_trades):
    """Conecta los agentes de Alpaca: Monitor → Analista → Optimizador → Verificador"""
    try:
        # 1. Monitor
        monitor_response = requests.get(f"{BASE_URL}/monitor", timeout=15)
        print(f"Monitor Alpaca: {monitor_response.status_code}")

        # 2. Analista
        analyst_response = requests.get(f"{BASE_URL}/analyze", timeout=30)
        print(f"Analista Alpaca: {analyst_response.status_code}")

        # 3. Optimizador si hay suficientes operaciones
        if len(alpaca_trades) >= 5:
            optimizer_response = requests.get(f"{BASE_URL}/optimize", timeout=30)
            print(f"Optimizador Alpaca: {optimizer_response.status_code}")

        # 4. Verificador
        verify_response = requests.get(f"{BASE_URL}/verify", timeout=10)
        print(f"Verificador Alpaca: {verify_response.status_code}")

        print("Pipeline Alpaca completado")
    except Exception as e:
        print(f"Error pipeline Alpaca: {e}")

def scheduler_loop_alpaca(get_trades_fn):
    """Loop principal del scheduler de Alpaca"""
    print("Scheduler Alpaca iniciado")
    last_pipeline   = None
    last_open_check = None

    while True:
        now     = datetime.utcnow()
        hour_arg = (now.hour - 3) % 24
        minute  = now.minute
        today   = now.date()
        weekday = now.weekday()  # 0=lunes, 4=viernes

        # Solo verificar en días de semana
        if weekday < 5:

            # Antes de apertura del mercado (10:20 AM Argentina)
            if hour_arg == 10 and minute == 20 and last_open_check != today:
                last_open_check = today
                active, balance = check_webhook()
                if active:
                    send_telegram(f"[OK] Alpaca Bot activo\nBalance: ${balance:,.2f}\nMercado abre en 10 min")
                else:
                    send_telegram(f"[ALERTA] Alpaca Bot no responde!\nVerificá el servidor de Render.")
                time.sleep(70)
                continue

            # Aviso cierre de mercado (4:50 PM Argentina)
            elif hour_arg == 16 and minute == 50:
                send_telegram(f"[INFO] Mercado Alpaca cierra en 10 minutos")
                time.sleep(70)
                continue

            # Pipeline diario después del cierre (5:30 PM Argentina)
            elif hour_arg == 17 and minute == 30 and last_pipeline != today:
                last_pipeline = today
                trades = get_trades_fn()
                print("Ejecutando pipeline diario Alpaca...")
                run_agent_pipeline_alpaca(trades)
                time.sleep(70)
                continue

        time.sleep(30)

def start_scheduler_alpaca(get_trades_fn):
    """Inicia el scheduler de Alpaca en un thread separado"""
    thread = threading.Thread(target=scheduler_loop_alpaca, args=(get_trades_fn,), daemon=True)
    thread.start()
    print("Scheduler Alpaca iniciado en background")
