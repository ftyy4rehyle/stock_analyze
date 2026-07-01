import logging
from datetime import datetime, timedelta

import httpx
import yfinance as yf

from twse_client import get_json

logger = logging.getLogger(__name__)

TWSE_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
TPEX_QUOTES_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"


def _fetch_twse(symbol: str) -> dict | None:
    """上市股票（TWSE）"""
    date = datetime.now().strftime("%Y%m%d")
    data = get_json(TWSE_URL, {"response": "json", "date": date, "stockNo": symbol})
    if not data or data.get("stat") != "OK" or not data.get("data"):
        logger.warning("TWSE no data for %s, trying prev month", symbol)
        prev = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y%m%d")
        data = get_json(TWSE_URL, {"response": "json", "date": prev, "stockNo": symbol})
        if not data or data.get("stat") != "OK" or not data.get("data"):
            logger.warning("TWSE prev month also no data for %s", symbol)
            return None

    rows = data["data"]
    latest = rows[-1]
    # 欄位：日期, 成交股數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, 漲跌價差, 成交筆數
    close = float(latest[6].replace(",", ""))
    change_str = latest[7].replace(",", "").strip()

    try:
        change = float(change_str.replace("+", "").replace("X", "0"))
        if "▼" in change_str or "-" in change_str:
            change = -abs(change)
    except ValueError:
        change = 0.0

    change_pct = round((change / (close - change)) * 100, 2) if (close - change) != 0 else 0
    title = data.get("title", "")
    parts = title.split()
    name = parts[2] if len(parts) >= 3 else symbol

    return {
        "symbol": symbol,
        "name": name,
        "price": close,
        "change": round(change, 2),
        "change_pct": change_pct,
    }


def _fetch_tpex(symbol: str) -> dict | None:
    """上櫃股票（TPEx）- 用新版 dailyQuotes API，回傳當日行情"""
    now = datetime.now()
    for delta in range(5):
        dt = now - timedelta(days=delta)
        date_str = dt.strftime("%Y%m%d")
        try:
            resp = httpx.get(
                TPEX_QUOTES_URL,
                params={"date": date_str, "response": "json"},
                timeout=15,
            )
            tables = resp.json().get("tables", [])
            if not tables:
                continue
            rows = tables[0].get("data", [])
            for row in rows:
                if str(row[0]).strip() == symbol:
                    close = float(str(row[2]).replace(",", ""))
                    try:
                        change = float(str(row[3]).replace(",", ""))
                    except ValueError:
                        change = 0.0
                    prev_close = close - change
                    change_pct = round((change / prev_close) * 100, 2) if prev_close != 0 else 0
                    return {
                        "symbol": symbol,
                        "name": str(row[1]),
                        "price": close,
                        "change": round(change, 2),
                        "change_pct": change_pct,
                    }
        except Exception as e:
            logger.warning("TPEx dailyQuotes error [%s] date=%s: %s", symbol, date_str, e)
            continue
    return None


def get_stock_price(symbol: str) -> dict | None:
    """查詢台股收盤價，先試 TWSE，失敗再試 TPEx"""
    symbol = symbol.strip().upper().replace(".TWO", "").replace(".TW", "")

    try:
        result = _fetch_twse(symbol)
        if result:
            return result
        return _fetch_tpex(symbol)
    except Exception as e:
        logger.error("get_stock_price error [%s]: %s", symbol, e)
        return None


def format_stock_message(data: dict) -> str:
    arrow = "▲" if data["change"] >= 0 else "▼"
    sign = "+" if data["change"] >= 0 else ""

    return (
        f"📊 {data['name']} ({data['symbol']})\n"
        f"現價：{data['price']} 元\n"
        f"漲跌：{arrow} {sign}{data['change']} ({sign}{data['change_pct']}%)\n"
        f"\n⚠️ 資料為收盤價，非即時報價"
    )
