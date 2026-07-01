from datetime import datetime, timedelta

import yfinance as yf

from twse_client import get_json

TWSE_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"


def _normalize(symbol: str) -> str:
    return symbol.strip().upper().replace(".TWO", "").replace(".TW", "")


def _fetch_month(symbol: str, date: str) -> list[float]:
    """抓單月收盤價列表 - TWSE 上市"""
    data = get_json(TWSE_URL, {"response": "json", "date": date, "stockNo": symbol})
    if not data or data.get("stat") != "OK" or not data.get("data"):
        return []
    prices = []
    for row in data["data"]:
        try:
            prices.append(float(row[6].replace(",", "")))
        except ValueError:
            continue
    return prices


def _fetch_history_yfinance(symbol: str, months: int) -> list[float]:
    """上櫃股票歷史收盤價 - yfinance（TPEx 用 .TWO 後綴）"""
    try:
        ticker = yf.Ticker(f"{symbol}.TWO")
        hist = ticker.history(period=f"{months}mo")
        if hist.empty:
            return []
        return [round(float(v), 2) for v in hist["Close"].tolist()]
    except Exception:
        return []


def get_history(symbol: str, months: int = 4) -> list[float]:
    """取得近 N 個月收盤價（預設 4 個月，足夠算 MA60）"""
    symbol = _normalize(symbol)
    now = datetime.now()

    month_list = []
    d = now
    for _ in range(months):
        month_list.insert(0, d)
        d = d.replace(day=1) - timedelta(days=1)

    # 先試 TWSE
    prices = []
    for d in month_list:
        prices.extend(_fetch_month(symbol, d.strftime("%Y%m%d")))
    if prices:
        return prices

    # TWSE 無資料，改用 yfinance（上櫃）
    return _fetch_history_yfinance(symbol, months)


def calc_ma(prices: list[float], period: int) -> float | None:
    if len(prices) < period:
        return None
    return round(sum(prices[-period:]) / period, 2)


def calc_rsi(prices: list[float], period: int = 14) -> float | None:
    if len(prices) < period + 1:
        return None
    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    recent = changes[-period:]
    gains = [c for c in recent if c > 0]
    losses = [-c for c in recent if c < 0]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def get_indicators(symbol: str) -> dict | None:
    """回傳技術指標，失敗回傳 None"""
    prices = get_history(symbol)
    if len(prices) < 20:
        return None

    return {
        "symbol": _normalize(symbol),
        "price": prices[-1],
        "ma5": calc_ma(prices, 5),
        "ma20": calc_ma(prices, 20),
        "ma60": calc_ma(prices, 60),
        "rsi": calc_rsi(prices, 14),
    }
