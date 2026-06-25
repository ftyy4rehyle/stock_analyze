from datetime import datetime, timedelta

from twse_client import get_json

TWSE_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"


def _fetch_month(symbol: str, date: str) -> list[float]:
    """抓單月收盤價列表"""
    data = get_json(TWSE_URL, {"response": "json", "date": date, "stockNo": symbol})
    if not data or data.get("stat") != "OK" or not data.get("data"):
        return []
    return [float(row[6].replace(",", "")) for row in data["data"]]


def get_history(symbol: str, months: int = 4) -> list[float]:
    """取得近 N 個月收盤價（預設 4 個月，足夠算 MA60）"""
    now = datetime.now()
    dates = []
    d = now
    for _ in range(months):
        dates.insert(0, d.strftime("%Y%m%d"))
        d = d.replace(day=1) - timedelta(days=1)

    prices = []
    for date in dates:
        prices.extend(_fetch_month(symbol, date))
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
        "ma60": calc_ma(prices, 60),
        "rsi": calc_rsi(prices, 14),
    }
