from datetime import datetime, timedelta

import httpx

TWSE_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"


def _fetch_month(symbol: str, date: str) -> list[float]:
    """抓單月收盤價列表"""
    resp = httpx.get(
        TWSE_URL,
        params={"response": "json", "date": date, "stockNo": symbol},
        timeout=10,
    )
    data = resp.json()
    if data.get("stat") != "OK" or not data.get("data"):
        return []
    return [float(row[6].replace(",", "")) for row in data["data"]]


def get_history(symbol: str) -> list[float]:
    """取得近兩個月收盤價（至少 25 筆才夠算 MA20+RSI）"""
    now = datetime.now()
    this_month = now.strftime("%Y%m%d")
    prev_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y%m%d")

    prices = _fetch_month(symbol, prev_month) + _fetch_month(symbol, this_month)
    return prices


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
        "symbol": symbol,
        "price": prices[-1],
        "ma5": calc_ma(prices, 5),
        "ma20": calc_ma(prices, 20),
        "rsi": calc_rsi(prices, 14),
    }
