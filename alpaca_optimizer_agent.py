import requests
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8957492846:AAGophSxXOSZGT4Gd1cLTNOICzxpZIH5wEU")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6518133529")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}")

def run_optimization_alpaca(trades_data, params_actuales):
    """Sugiere ajustes a los parametros del bot de Alpaca"""
    if len(trades_data) < 5:
        return {"message": "Necesitas al menos 5 operaciones para optimizar"}
    
    total = len(trades_data)
    wins = sum(1 for t in trades_data if t['profit'] > 0)
    losses = total - wins
    win_rate = wins / total * 100
    total_profit = sum(t['profit'] for t in trades_data)
    
    avg_win  = sum(t['profit'] for t in trades_data if t['profit'] > 0) / wins if wins > 0 else 0
    avg_loss = sum(t['profit'] for t in trades_data if t['profit'] < 0) / losses if losses > 0 else 0
    
    sugerencias = []
    params_sugeridos = dict(params_actuales)
    
    # Regla 1: Win rate muy bajo → ajustar SL/TP
    if win_rate < 40:
        sugerencias.append("Win rate bajo - considerar reducir Stop Loss al 0.7%")
        params_sugeridos['stop_loss_pct'] = 0.7
    
    # Regla 2: Win rate alto pero pocas ganancias → subir Take Profit
    if win_rate > 60 and avg_win < abs(avg_loss):
        sugerencias.append("Buena tasa de aciertos - considerar subir Take Profit al 2.5%")
        params_sugeridos['take_profit_pct'] = 2.5
    
    # Regla 3: Muchas perdidas grandes → bajar PCT_CAPITAL
    if avg_loss < -200:
        sugerencias.append("Perdidas grandes - considerar reducir capital por operacion al 15%")
        params_sugeridos['pct_capital'] = 15
    
    # Regla 4: P&L positivo consistente → se puede escalar
    if total_profit > 200 and win_rate > 55:
        sugerencias.append("Resultados consistentes - se puede subir capital al 25%")
        params_sugeridos['pct_capital'] = 25
    
    report = f"[OPTIMIZADOR ALPACA] {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
    report += f"Analisis de {total} operaciones:\n"
    report += f"  Win rate: {win_rate:.1f}%\n"
    report += f"  P&L total: ${total_profit:.2f}\n"
    report += f"  Ganancia promedio: ${avg_win:.2f}\n"
    report += f"  Perdida promedio: ${avg_loss:.2f}\n\n"
    
    if sugerencias:
        report += "Sugerencias:\n"
        for s in sugerencias:
            report += f"  - {s}\n"
    else:
        report += "Sistema funcionando bien, sin cambios sugeridos\n"
    
    send_telegram(report)
    
    return {
        "stats": {
            "total": total,
            "win_rate": round(win_rate, 1),
            "total_profit": round(total_profit, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2)
        },
        "sugerencias": sugerencias,
        "params_sugeridos": params_sugeridos
    }
