from datetime import datetime, timedelta

import yfinance as yf

from analysis import calc_rsi
from twse_client import get_json

TWSE_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"


def _normalize(symbol: str) -> str:
    return symbol.strip().upper().replace(".TWO", "").replace(".TW", "")


def _roc_to_iso(date_str: str) -> str:
    """113/06/16 → 2024-06-16"""
    parts = date_str.strip().split("/")
    year = int(parts[0]) + 1911
    return f"{year}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def _fetch_month_ohlcv(symbol: str, date: str) -> list[dict]:
    """TWSE 單月 OHLCV"""
    data = get_json(TWSE_URL, {"response": "json", "date": date, "stockNo": symbol})
    if not data or data.get("stat") != "OK" or not data.get("data"):
        return []
    result = []
    for row in data["data"]:
        try:
            result.append({
                "time": _roc_to_iso(row[0]),
                "open": float(row[3].replace(",", "")),
                "high": float(row[4].replace(",", "")),
                "low": float(row[5].replace(",", "")),
                "close": float(row[6].replace(",", "")),
            })
        except (ValueError, IndexError):
            continue
    return result


def _fetch_ohlcv_yfinance(symbol: str, months: int) -> list[dict]:
    """上櫃股票 OHLCV - yfinance（TPEx 用 .TWO 後綴）"""
    try:
        ticker = yf.Ticker(f"{symbol}.TWO")
        hist = ticker.history(period=f"{months}mo")
        if hist.empty:
            return []
        result = []
        for date, row in hist.iterrows():
            result.append({
                "time": date.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
            })
        return result
    except Exception:
        return []


def get_chart_data(symbol: str) -> dict | None:
    """回傳 K 線圖資料：OHLCV + MA5 + MA20 + RSI（近 3 個月）"""
    symbol = _normalize(symbol)
    now = datetime.now()

    month_list = []
    d = now
    for _ in range(3):
        month_list.insert(0, d)
        d = (d.replace(day=1) - timedelta(days=1))

    # 先試 TWSE
    candles = []
    for d in month_list:
        candles.extend(_fetch_month_ohlcv(symbol, d.strftime("%Y%m%d")))

    # TWSE 無資料，改用 yfinance（上櫃）
    if not candles:
        candles = _fetch_ohlcv_yfinance(symbol, 3)

    if not candles:
        return None

    # 去重並排序
    seen: set[str] = set()
    unique = []
    for c in candles:
        if c["time"] not in seen:
            seen.add(c["time"])
            unique.append(c)
    candles = sorted(unique, key=lambda x: x["time"])

    closes = [c["close"] for c in candles]

    # MA 序列
    ma5_series = []
    ma20_series = []
    for i in range(len(candles)):
        if i >= 4:
            ma5_series.append({
                "time": candles[i]["time"],
                "value": round(sum(closes[i - 4:i + 1]) / 5, 2),
            })
        if i >= 19:
            ma20_series.append({
                "time": candles[i]["time"],
                "value": round(sum(closes[i - 19:i + 1]) / 20, 2),
            })

    # RSI 序列
    rsi_series = []
    for i in range(14, len(closes)):
        val = calc_rsi(closes[:i + 1], 14)
        if val is not None:
            rsi_series.append({"time": candles[i]["time"], "value": val})

    return {
        "symbol": symbol,
        "candles": candles,
        "ma5": ma5_series,
        "ma20": ma20_series,
        "rsi": rsi_series,
    }
