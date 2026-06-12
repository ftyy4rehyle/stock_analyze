import yfinance as yf


def get_stock_price(symbol: str) -> dict | None:
    """查詢台股收盤價，symbol 傳入代號如 '2330'，自動補 .TW"""
    if symbol.startswith("^") or symbol.endswith(".TW"):
        ticker_symbol = symbol
    else:
        ticker_symbol = f"{symbol}.TW"
    ticker = yf.Ticker(ticker_symbol)

    try:
        hist = ticker.history(period="5d", auto_adjust=False)
        if hist.empty:
            return None

        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else latest

        price = round(float(latest["Close"]), 2)
        prev_close = round(float(prev["Close"]), 2)
        change = round(price - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0

        name = ticker.info.get("shortName") or ticker.info.get("longName") or symbol

        return {
            "symbol": symbol,
            "name": name,
            "price": price,
            "change": change,
            "change_pct": change_pct,
        }
    except Exception:
        return None


def format_stock_message(data: dict) -> str:
    arrow = "▲" if data["change"] >= 0 else "▼"
    sign = "+" if data["change"] >= 0 else ""

    return (
        f"📊 {data['name']} ({data['symbol']})\n"
        f"現價：{data['price']} 元\n"
        f"漲跌：{arrow} {sign}{data['change']} ({sign}{data['change_pct']}%)\n"
        f"\n⚠️ 資料僅供參考，非即時報價"
    )
