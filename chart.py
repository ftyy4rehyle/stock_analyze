from datetime import datetime, timedelta

import httpx

from analysis import calc_rsi

TWSE_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"


def _roc_to_iso(date_str: str) -> str:
    """113/06/16 → 2024-06-16"""
    parts = date_str.strip().split("/")
    year = int(parts[0]) + 1911
    return f"{year}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def _fetch_month_ohlcv(symbol: str, date: str) -> list[dict]:
    try:
        resp = httpx.get(
            TWSE_URL,
            params={"response": "json", "date": date, "stockNo": symbol},
            timeout=10,
            follow_redirects=True,
        )
        data = resp.json()
        if data.get("stat") != "OK" or not data.get("data"):
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
    except Exception:
        return []


def get_chart_data(symbol: str) -> dict | None:
    """回傳 K 線圖資料：OHLCV + MA5 + MA20 + RSI（近 3 個月）"""
    now = datetime.now()
    months = []
    d = now
    for _ in range(3):
        months.insert(0, d.strftime("%Y%m%d"))
        d = (d.replace(day=1) - timedelta(days=1))

    candles = []
    for m in months:
        candles.extend(_fetch_month_ohlcv(symbol, m))

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
