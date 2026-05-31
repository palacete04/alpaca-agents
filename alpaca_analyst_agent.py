import requests
import os
from datetime import datetime, timedelta
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

def get_market_data(symbol, days=30):
    """Descarga datos historicos de un simbolo desde Alpaca"""
    try:
        api = get_alpaca_client()
        end = datetime.now()
        start = end - timedelta(days=days)
        barras = api.get_bars(
            symbol,
            tradeapi.TimeFrame.Day,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d")
        ).df
        return barras
    except Exception as e:
        print(f"Error obteniendo datos de {symbol}: {e}")
        return None

def calcular_indicadores(df):
    """Calcula EMA50, EMA200, RSI y tendencia"""
    if df is None or len(df) < 10:
        return None
    
    df = df.copy()
    df['ema50']  = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Retorno ultimos 5 dias
    df['retorno_5d'] = df['close'].pct_change(5) * 100
    
    ultimo = df.iloc[-1]
    tendencia = "ALCISTA" if ultimo['ema50'] > ultimo['ema200'] else "BAJISTA"
    
    return {
        "precio": round(ultimo['close'], 2),
        "ema50": round(ultimo['ema50'], 2),
        "ema200": round(ultimo['ema200'], 2),
        "rsi": round(ultimo['rsi'], 1),
        "tendencia": tendencia,
        "retorno_5d": round(ultimo['retorno_5d'], 2),
        "volumen": int(ultimo['volume'])
    }

def sugerir_estrategias(indicadores):
    """Sugiere estrategias basadas en los indicadores actuales"""
    sugerencias = []
    
    if not indicadores:
        return sugerencias
    
    ind = indicadores
    
    # MA Crossover
    if ind['tendencia'] == "ALCISTA":
        sugerencias.append("MA Crossover 50/200: FAVORABLE (tendencia alcista activa)")
    else:
        sugerencias.append("MA Crossover 50/200: PRECAUCION (tendencia bajista)")
    
    # RSI Mean Reversion
    if ind['rsi'] < 35:
        sugerencias.append(f"Mean Reversion RSI: OPORTUNIDAD DE COMPRA (RSI={ind['rsi']})")
    elif ind['rsi'] > 70:
        sugerencias.append(f"Mean Reversion RSI: ZONA DE VENTA (RSI={ind['rsi']})")
    else:
        sugerencias.append(f"Mean Reversion RSI: NEUTRAL (RSI={ind['rsi']})")
    
    # Momentum
    if ind['retorno_5d'] > 2:
        sugerencias.append(f"Momentum: POSITIVO (+{ind['retorno_5d']}% en 5 dias)")
    elif ind['retorno_5d'] < -2:
        sugerencias.append(f"Momentum: NEGATIVO ({ind['retorno_5d']}% en 5 dias)")
    
    return sugerencias

def run_analysis_alpaca():
    """Ejecuta analisis completo de SPY, QQQ e IWM"""
    simbolos = ["SPY", "QQQ", "IWM"]
    resultados = {}
    
    report = f"[ANALISTA ALPACA] {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
    
    for sym in simbolos:
        df = get_market_data(sym)
        ind = calcular_indicadores(df)
        
        if ind:
            sugerencias = sugerir_estrategias(ind)
            resultados[sym] = {"indicadores": ind, "sugerencias": sugerencias}
            
            report += f"{sym}: ${ind['precio']} | Tendencia: {ind['tendencia']}\n"
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
