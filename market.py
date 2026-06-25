from datetime import datetime, timedelta

from twse_client import get_json

TWSE_INDEX_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"


def get_taiex() -> dict | None:
    """回傳大盤（發行量加權股價指數）當日收盤資訊"""
    date = datetime.now().strftime("%Y%m%d")
    result = _fetch_taiex(date)
    if result:
        return result
    # 今日無資料時（假日/盤前）改抓上個交易日
    prev = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    return _fetch_taiex(prev)


def _fetch_taiex(date: str) -> dict | None:
    data = get_json(TWSE_INDEX_URL, {"date": date, "type": "IND", "response": "json"})
    if not data or data.get("stat") != "OK":
        return None
    for row in data.get("data", []):
        if "發行量加權股價指數" in row[0]:
            # 欄位：指數名稱, 收盤, 漲跌點數, 漲跌百分比
            close = float(row[1].replace(",", ""))
            change_str = row[2].replace(",", "").strip()
            change_pct_str = row[3].replace(",", "").strip()
            try:
                change = float(change_str)
                change_pct = float(change_pct_str.replace("%", ""))
            except ValueError:
                change, change_pct = 0.0, 0.0
            return {
                "close": close,
                "change": change,
                "change_pct": change_pct,
            }
    return None


def format_taiex(data: dict) -> str:
    arrow = "▲" if data["change"] >= 0 else "▼"
    sign = "+" if data["change"] >= 0 else ""
    return f"大盤 {data['close']:,.0f} 點 {arrow} {sign}{data['change']:,.0f} ({sign}{data['change_pct']:.2f}%)"
