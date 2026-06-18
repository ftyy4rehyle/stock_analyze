import os

import anthropic

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def get_ai_analysis(
    name: str,
    indicators: dict,
    news: list[str] | None = None,
    taiex: str | None = None,
) -> str:
    """
    接收技術指標、新聞標題、大盤狀態，呼叫 Claude Haiku 生成買賣建議。
    回傳格式化的 LINE 推播文字段落。
    """
    symbol = indicators["symbol"]
    price = indicators["price"]
    ma5 = indicators.get("ma5")
    ma20 = indicators.get("ma20")
    rsi = indicators.get("rsi")

    news_section = ""
    if news:
        news_lines = "\n".join(f"- {n}" for n in news)
        news_section = f"\n最新相關新聞：\n{news_lines}"

    market_section = ""
    if taiex:
        market_section = f"\n今日大盤：{taiex}"

    prompt = f"""你是一位台股技術分析師，根據以下資訊，用繁體中文生成簡短的分析建議。

股票：{name}（{symbol}）
現價：{price} 元
MA5：{ma5}
MA20：{ma20}
RSI（14日）：{rsi}{market_section}{news_section}

請輸出以下格式，每行一條，不要多餘說明：
技術分析：[一句描述 RSI 狀態與均線多空，可結合大盤與新聞]
建議：[一句操作建議]
風險：⚠️ [一句風險提示]

注意：
- 若 RSI > 70，說明超買；RSI < 30，說明超賣
- 若 MA5 > MA20，說明短期偏多；MA5 < MA20，說明短期偏弱
- 若有重大新聞利多/利空，可在分析中點出
- 建議須保守，強調僅供個人參考，非投資建議"""

    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=250,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()
