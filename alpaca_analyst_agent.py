import requests
import os
from datetime import datetime, timedelta

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8957492846:AAGophSxXOSZGT4Gd1cLTNOICzxpZIH5wEU")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6518133529")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}")

def get_market_data(symbol, days=30):
    """Descarga datos historicos desde Yahoo Finance"""
    try:
        end = datetime.now()
        start = end - timedelta(days=days)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {
            "period1": int(start.timestamp()),
            "period2": int(end.timestamp()),
            "interval": "1d",
            "includePrePost": False
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, params=params, headers=headers, timeout=15)
        data = response.json()
        result = data["chart"]["result"][0]
        closes  = result["indicators"]["quote"][0]["close"]
        volumes = result["indicators"]["quote"][0]["volume"]
        closes  = [c for c in closes if c is not None]
        volumes = [v for v in volumes if v is not None]
        return closes, volumes
    except Exception as e:
        print(f"Error obteniendo datos de {symbol}: {e}")
        return [], []

def calcular_indicadores(closes, volumes):
    """Calcula EMA50, EMA200, RSI y tendencia"""
    if len(closes) < 10:
        return None

    # EMA simple
    def ema(data, span):
        k = 2 / (span + 1)
        result = [data[0]]
        for price in data[1:]:
            result.append(price * k + result[-1] * (1 - k))
        return result

    ema50  = ema(closes, 50)[-1] if len(closes) >= 50 else ema(closes, len(closes))[-1]
    ema200 = ema(closes, 200)[-1] if len(closes) >= 200 else ema(closes, len(closes))[-1]

    # RSI
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains  = [d if d > 0 else 0 for d in deltas[-14:]]
    losses = [-d if d < 0 else 0 for d in deltas[-14:]]
    avg_gain = sum(gains) / 14 if gains else 0
    avg_loss = sum(losses) / 14 if losses else 1
    rs  = avg_gain / avg_loss if avg_loss > 0 else 0
    rsi = 100 - (100 / (1 + rs))

    precio = closes[-1]
    retorno_5d = ((closes[-1] - closes[-6]) / closes[-6] * 100) if len(closes) >= 6 else 0
    tendencia = "ALCISTA" if ema50 > ema200 else "BAJISTA"

    return {
        "precio": round(precio, 2),
        "ema50": round(ema50, 2),
        "ema200": round(ema200, 2),
        "rsi": round(rsi, 1),
        "tendencia": tendencia,
        "retorno_5d": round(retorno_5d, 2),
        "volumen_promedio": int(sum(volumes[-5:]) / 5) if volumes else 0
    }

def sugerir_estrategias(ind):
    sugerencias = []
    if ind['tendencia'] == "ALCISTA":
        sugerencias.append("MA Crossover 50/200: FAVORABLE (tendencia alcista)")
    else:
        sugerencias.append("MA Crossover 50/200: PRECAUCION (tendencia bajista)")
    if ind['rsi'] < 35:
        sugerencias.append(f"Mean Reversion RSI: OPORTUNIDAD COMPRA (RSI={ind['rsi']})")
    elif ind['rsi'] > 70:
        sugerencias.append(f"Mean Reversion RSI: ZONA DE VENTA (RSI={ind['rsi']})")
    else:
        sugerencias.append(f"Mean Reversion RSI: NEUTRAL (RSI={ind['rsi']})")
    if ind['retorno_5d'] > 2:
        sugerencias.append(f"Momentum: POSITIVO (+{ind['retorno_5d']}% en 5 dias)")
    elif ind['retorno_5d'] < -2:
        sugerencias.append(f"Momentum: NEGATIVO ({ind['retorno_5d']}% en 5 dias)")
    return sugerencias

def run_analysis_alpaca():
    simbolos = ["SPY", "QQQ", "IWM"]
    resultados = {}
    report = f"[ANALISTA ALPACA] {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"

    for sym in simbolos:
        closes, volumes = get_market_data(sym)
        ind = calcular_indicadores(closes, volumes)
        if ind:
            sugerencias = sugerir_estrategias(ind)
            resultados[sym] = {"indicadores": ind, "sugerencias": sugerencias}
            report += f"{sym}: ${ind['precio']} | {ind['tendencia']}\n"
            report += f"  EMA50: ${ind['ema50']} | EMA200: ${ind['ema200']}\n"
            report += f"  RSI: {ind['rsi']} | Retorno 5d: {ind['retorno_5d']}%\n"
            report += f"  Estrategias:\n"
            for s in sugerencias:
                report += f"    - {s}\n"
            report += "\n"
        else:
            report += f"{sym}: Error al obtener datos\n\n"

    send_telegram(report)
    return resultados
