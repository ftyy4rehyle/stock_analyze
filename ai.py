import os

import anthropic

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def get_ai_analysis(name: str, indicators: dict) -> str:
    """
    接收技術指標，呼叫 Claude Haiku 生成買賣建議。
    回傳格式化的 LINE 推播文字段落。
    """
    symbol = indicators["symbol"]
    price = indicators["price"]
    ma5 = indicators.get("ma5")
    ma20 = indicators.get("ma20")
    rsi = indicators.get("rsi")

    ma_str = f"MA5={ma5}, MA20={ma20}" if ma5 and ma20 else "均線資料不足"
    rsi_str = str(rsi) if rsi is not None else "RSI 資料不足"

    prompt = f"""你是一位台股技術分析師，根據以下技術指標，用繁體中文生成簡短的分析建議。

股票：{name}（{symbol}）
現價：{price} 元
MA5：{ma5}
MA20：{ma20}
RSI（14日）：{rsi}

請輸出以下格式，每行一條，不要多餘說明：
技術分析：[一句描述 RSI 狀態與均線多空]
建議：[一句操作建議]
風險：⚠️ [一句風險提示]

注意：
- 若 RSI > 70，說明超買；RSI < 30，說明超賣
- 若 MA5 > MA20，說明短期偏多；MA5 < MA20，說明短期偏弱
- 建議須保守，強調僅供個人參考，非投資建議"""

    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()
