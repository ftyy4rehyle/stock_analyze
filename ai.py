import os

import anthropic

_client = None

DEFAULT_RULES = """策略：保守波段

買進條件（須同時符合）：
- MA20 > MA60（中期趨勢向上）
- 股價 > MA20（站上短期均線）
- 量 > 5MA（成交量站上 5 日均量；若無量能資料，僅以提示方向呈現）

股票波動分類（用於決定停損%，需綜合市值、波動率、Beta、成交量、產業、價格走勢判斷）：
- ETF：停損 -5%~-7%
- 低波動股票：停損 -5%~-7%
- 中波動股票：停損 -8%
- 高波動股票：停損 -10%

停損：若跌破 MA20 且目前已虧損，優先出場，不等到觸及停損比例。

停利（分批）：
- 獲利達 20% → 先停利 30% 持股
- 剩餘持股 → 跌破 MA20 全部賣出
- 未達 20% 獲利時，僅依 MA20 判斷是否續抱

出場優先順序：1. 停損　2. 停利　3. MA20 趨勢出場　4. 持有"""


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
    position: dict | None = None,
    user_rules: str | None = None,
) -> str:
    """
    接收技術指標、新聞、大盤、持股資訊，呼叫 Claude Haiku 生成買賣建議。
    position 為 None 或 cost 為 None 時 → 進場評估模式
    position 有 cost 時 → 持有/賣出評估模式（套用個人規則）
    user_rules 有值時優先使用，否則 fallback 用系統預設規則（DEFAULT_RULES）
    """
    rules = user_rules.strip() if user_rules else DEFAULT_RULES
    symbol = indicators["symbol"]
    price = indicators["price"]
    ma5 = indicators.get("ma5")
    ma20 = indicators.get("ma20")
    ma60 = indicators.get("ma60")
    rsi = indicators.get("rsi")

    news_section = ""
    if news:
        news_lines = "\n".join(f"- {n}" for n in news)
        news_section = f"\n最新相關新聞：\n{news_lines}"

    market_section = f"\n今日大盤：{taiex}" if taiex else ""

    has_cost = position and position.get("cost")

    if has_cost:
        cost = position["cost"]
        gain_pct = round((price - cost) / cost * 100, 2)
        mode_section = f"""
【持有中】
買入成本：{cost} 元
目前損益：{gain_pct}%

請依照下方「個人交易規則」的停損/停利/MA20 出場優先順序，判斷目前應該：停損、停利（分批）、續抱、或依 MA20 出場。
請先說明股票波動分類（ETF/低/中/高波動）與依據，再給出明確建議。"""
        output_format = """技術分析：[一句描述 RSI 狀態、均線多空，可結合大盤與新聞]
波動分類：[ETF/低波動/中波動/高波動，並簡述判斷依據]
持有建議：[依個人規則判斷：停損 / 分批停利 / 續抱 / MA20 出場，給明確理由]
風險：⚠️ [一句風險提示]"""
    else:
        mode_section = """
【尚未持有，評估進場】
請依照下方「個人交易規則」的買進條件，判斷目前是否符合進場時機。"""
        output_format = """技術分析：[一句描述 RSI 狀態、均線多空，可結合大盤與新聞]
進場評估：
✅ 或 ❌ MA20>MA60：[符合/不符合，附數值]
✅ 或 ❌ 股價>MA20：[符合/不符合，附數值]
✅ 或 ❌ 量>5MA：[符合/不符合，或說明資料不足]
建議：[符合則建議可進場，不符合則說明還缺什麼條件]
風險：⚠️ [一句風險提示]"""

    prompt = f"""你是一位台股技術分析師，根據以下資訊與「個人交易規則」，用繁體中文生成分析建議。

股票：{name}（{symbol}）
現價：{price} 元
MA5：{ma5}
MA20：{ma20}
MA60：{ma60}
RSI（14日）：{rsi}{market_section}{news_section}
{mode_section}

個人交易規則：
{rules}

請輸出以下格式，每行一條，不要多餘說明：
{output_format}

注意：
- 若 RSI > 70，說明超買；RSI < 30，說明超賣
- 若有重大新聞利多/利空，可在分析中點出
- 建議須保守，強調僅供個人參考，非投資建議
- 格式要求：禁止使用 ✓ ✗ ✔ ✘ 等小型勾叉符號，一律用 ✅ ❌ 表示符合/不符合；每個條件項目獨立一行，不要把多個條件擠在同一行用符號分隔
- 純文字輸出，禁止使用 Markdown 語法（不要 ** 粗體、不要 # 標題、不要用 - 或 * 條列符號），純粹用換行分段即可
- 每一句務必完整講完，不要中途斷句"""

    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()
