import yfinance as yf


def get_stock_price(symbol: str) -> dict | None:
    """查詢台股收盤價，symbol 傳入代號如 '2330'，自動補 .TW"""
    ticker_symbol = f"{symbol}.TW" if not symbol.startswith("^") else symbol
    ticker = yf.Ticker(ticker_symbol)

    try:
        info = ticker.fast_info
        price = info.last_price
        prev_close = info.previous_close

        if price is None:
            return None

        change = price - prev_close
        change_pct = (change / prev_close) * 100 if prev_close else 0

        # 取得股票名稱（yfinance 台股 shortName 通常是英文，longName 有時為空）
        name = ticker.info.get("shortName") or ticker.info.get("longName") or symbol

        return {
            "symbol": symbol,
            "name": name,
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
        }
    except Exception:
        return None


def format_stock_message(data: dict) -> str:
    """將股價資料格式化為 LINE 推播文字"""
    arrow = "▲" if data["change"] >= 0 else "▼"
    sign = "+" if data["change"] >= 0 else ""

    return (
        f"📊 {data['name']} ({data['symbol']})\n"
        f"現價：{data['price']} 元\n"
        f"漲跌：{arrow} {sign}{data['change']} ({sign}{data['change_pct']}%)\n"
        f"\n⚠️ 資料僅供參考，非即時報價"
    )
