import logging
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

TWSE_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
TPEX_URL = "https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php"


def _fetch_twse(symbol: str) -> dict | None:
    """上市股票（TWSE）"""
    date = datetime.now().strftime("%Y%m%d")
    resp = httpx.get(
        TWSE_URL,
        params={"response": "json", "date": date, "stockNo": symbol},
        timeout=10,
    )
    data = resp.json()
    if data.get("stat") != "OK" or not data.get("data"):
        logger.warning("TWSE no data for %s stat=%s, trying prev month", symbol, data.get("stat"))
        prev = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y%m%d")
        resp = httpx.get(
            TWSE_URL,
            params={"response": "json", "date": prev, "stockNo": symbol},
            timeout=10,
        )
        data = resp.json()
        if data.get("stat") != "OK" or not data.get("data"):
            logger.warning("TWSE prev month also no data for %s", symbol)
            return None

    rows = data["data"]
    latest = rows[-1]
    # 欄位：日期, 成交股數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, 漲跌價差, 成交筆數
    close = float(latest[6].replace(",", ""))
    change_str = latest[7].replace(",", "").strip()

    # 漲跌符號在欄位前（有時帶 + / - 符號或 X）
    try:
        change = float(change_str.replace("+", "").replace("X", "0"))
        if "▼" in change_str or "-" in change_str:
            change = -abs(change)
    except ValueError:
        change = 0.0

    change_pct = round((change / (close - change)) * 100, 2) if (close - change) != 0 else 0
    name = data.get("title", "").split(" ")[1] if " " in data.get("title", "") else symbol

    return {
        "symbol": symbol,
        "name": name,
        "price": close,
        "change": round(change, 2),
        "change_pct": change_pct,
    }


def _fetch_tpex(symbol: str) -> dict | None:
    """上櫃股票（TPEx）"""
    now = datetime.now()
    # TPEx 使用民國年
    year = now.year - 1911
    date = f"{year}/{now.month:02d}"
    resp = httpx.get(
        TPEX_URL,
        params={"l": "zh-tw", "d": date, "s": symbol},
        timeout=10,
    )
    data = resp.json()
    rows = data.get("aaData", [])
    if not rows:
        return None

    latest = rows[-1]
    # 欄位：日期, 成交股數, 成交金額, 開盤, 最高, 最低, 收盤, 漲跌, 成交筆數
    close = float(latest[6].replace(",", ""))
    try:
        change = float(latest[7].replace(",", "").replace("+", ""))
    except ValueError:
        change = 0.0

    change_pct = round((change / (close - change)) * 100, 2) if (close - change) != 0 else 0

    return {
        "symbol": symbol,
        "name": symbol,
        "price": close,
        "change": round(change, 2),
        "change_pct": change_pct,
    }


def get_stock_price(symbol: str) -> dict | None:
    """查詢台股收盤價，先試 TWSE，失敗再試 TPEx"""
    symbol = symbol.strip().upper().replace(".TW", "")

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
