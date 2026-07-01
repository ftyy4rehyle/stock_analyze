from datetime import datetime, timedelta

import httpx

from analysis import calc_rsi
from twse_client import get_json

TWSE_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
TPEX_URL = "https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php"


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


def _fetch_month_ohlcv_tpex(symbol: str, year: int, month: int) -> list[dict]:
    """TPEx 單月 OHLCV"""
    date = f"{year - 1911}/{month:02d}"
    try:
        resp = httpx.get(TPEX_URL, params={"l": "zh-tw", "d": date, "s": symbol}, timeout=10)
        rows = resp.json().get("aaData", [])
    except Exception:
        return []
    result = []
    for row in rows:
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

    # TWSE 無資料，改試 TPEx
    if not candles:
        for d in month_list:
            candles.extend(_fetch_month_ohlcv_tpex(symbol, d.year, d.month))

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
