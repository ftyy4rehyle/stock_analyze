import base64
import hashlib
import hmac
import logging
import os
import time
from datetime import datetime

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

from ai import get_ai_analysis
from analysis import get_indicators
from db import (
    add_stock,
    get_all_notify_users,
    get_notify,
    get_rules,
    get_stocks,
    remove_stock,
    set_notify,
    set_rules,
)
from market import format_taiex, get_taiex
from news import get_stock_news
from stock import format_stock_message, get_stock_price
from web import router as web_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Bower Stock")
app.include_router(web_router)

LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
BROADCAST_SECRET = os.environ.get("BROADCAST_SECRET", "")


# ── LINE Webhook ──────────────────────────────────────────────────────────────

def verify_signature(body: bytes, signature: str) -> bool:
    digest = hmac.new(
        LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


async def reply_message(reply_token: str, text: str) -> None:
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(LINE_REPLY_URL, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("LINE reply failed: %s", resp.text)


# ── 指令處理 ──────────────────────────────────────────────────────────────────

async def handle_text(reply_token: str, user_id: str, text: str) -> None:
    text = text.strip()

    if text.startswith("/查股"):
        parts = text.split()
        if len(parts) < 2:
            await reply_message(reply_token, "請輸入股票代號，例如：/查股 2330")
            return
        symbol = parts[1].strip()
        data = get_stock_price(symbol)
        if data is None:
            await reply_message(reply_token, f"查無股票代號：{symbol}\n請確認代號是否正確（例如：2330、0050）")
        else:
            await reply_message(reply_token, format_stock_message(data))

    elif text.startswith("/追蹤"):
        parts = text.split()
        if len(parts) < 2:
            await reply_message(
                reply_token,
                "請輸入股票代號，例如：\n"
                "/追蹤 2330 — 觀察進場訊號\n"
                "/追蹤 2330 2350 — 已持有，成本 2350 元\n"
                "/追蹤 2330 2350 1000 — 已持有，成本 2350 元，1000 股",
            )
            return
        symbol = parts[1].strip()
        cost = None
        qty = None
        try:
            if len(parts) >= 3:
                cost = float(parts[2])
            if len(parts) >= 4:
                qty = float(parts[3])
        except ValueError:
            await reply_message(reply_token, "成本/股數請輸入數字，例如：/追蹤 2330 2350")
            return

        ok = add_stock(user_id, symbol, cost=cost, qty=qty)
        if ok:
            if cost:
                await reply_message(reply_token, f"✅ 已加入追蹤：{symbol}（成本 {cost} 元）")
            else:
                await reply_message(reply_token, f"✅ 已加入追蹤：{symbol}（觀察進場訊號）")
        else:
            await reply_message(reply_token, "追蹤清單已達上限（最多 10 支），請先取消追蹤部分股票。")

    elif text.startswith("/取消追蹤"):
        parts = text.split()
        if len(parts) < 2:
            await reply_message(reply_token, "請輸入股票代號，例如：/取消追蹤 2330")
            return
        symbol = parts[1].strip()
        ok = remove_stock(user_id, symbol)
        if ok:
            await reply_message(reply_token, f"✅ 已取消追蹤：{symbol}")
        else:
            await reply_message(reply_token, f"{symbol} 不在你的追蹤清單中。")

    elif text == "/我的股票":
        stocks = get_stocks(user_id)
        notify = get_notify(user_id)
        if not stocks:
            await reply_message(reply_token, "追蹤清單是空的，輸入 /追蹤 [代號] 開始追蹤。")
        else:
            notify_status = "開啟 ✅" if notify else "關閉 ❌"
            lines = []
            for s in stocks:
                if s.get("cost"):
                    price_data = get_stock_price(s["symbol"])
                    if price_data:
                        gain_pct = round((price_data["price"] - s["cost"]) / s["cost"] * 100, 2)
                        sign = "+" if gain_pct >= 0 else ""
                        lines.append(f"• {s['symbol']}（成本 {s['cost']}，{sign}{gain_pct}%）")
                    else:
                        lines.append(f"• {s['symbol']}（成本 {s['cost']}）")
                else:
                    lines.append(f"• {s['symbol']}（觀察中）")
            stock_list = "\n".join(lines)
            await reply_message(reply_token, f"📋 你的追蹤清單（{len(stocks)}/10）：\n{stock_list}\n\n每日推播：{notify_status}")

    elif text == "/推播開":
        set_notify(user_id, True)
        await reply_message(reply_token, "✅ 每日推播已開啟，收盤後約 15:00 推播。")

    elif text == "/推播關":
        set_notify(user_id, False)
        await reply_message(reply_token, "❌ 每日推播已關閉。")

    elif text.startswith("/設定規則"):
        content = text[len("/設定規則"):].strip()
        if not content:
            await reply_message(
                reply_token,
                "請在指令後輸入規則內容，例如：\n"
                "/設定規則 策略：積極。RSI<30買進，獲利15%停利，停損10%",
            )
            return
        set_rules(user_id, content)
        await reply_message(reply_token, f"✅ 已更新你的交易規則：\n{content}")

    elif text == "/我的規則":
        rules = get_rules(user_id)
        if rules:
            await reply_message(reply_token, f"📜 你的交易規則：\n{rules}")
        else:
            await reply_message(reply_token, "你尚未設定個人規則，目前套用系統預設規則（保守波段）。\n輸入 /設定規則 [內容] 自訂。")

    elif text == "/清除規則":
        set_rules(user_id, "")
        await reply_message(reply_token, "✅ 已清除個人規則，改用系統預設規則。")

    else:
        await reply_message(
            reply_token,
            "Bower Stock 指令列表：\n"
            "/查股 [代號] — 查詢股票現價\n"
            "/追蹤 [代號] — 觀察進場訊號\n"
            "/追蹤 [代號] [成本] — 已持有，追蹤賣出時機\n"
            "/追蹤 [代號] [成本] [股數] — 同上，含股數\n"
            "/取消追蹤 [代號] — 移除追蹤\n"
            "/我的股票 — 查看追蹤清單\n"
            "/推播開 / /推播關 — 開關每日推播\n"
            "/設定規則 [內容] — 自訂個人交易規則\n"
            "/我的規則 — 查看目前規則\n"
            "/清除規則 — 恢復系統預設規則",
        )


# ── LINE Push ─────────────────────────────────────────────────────────────────

async def push_message(user_id: str, text: str) -> None:
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(LINE_PUSH_URL, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("LINE push failed: %s", resp.text)


def build_stock_block(position: dict, taiex_str: str | None = None, user_rules: str | None = None) -> str | None:
    """取得單支股票的完整推播區塊文字，失敗回傳 None"""
    symbol = position["symbol"]
    price_data = get_stock_price(symbol)

    try:
        indicators = get_indicators(symbol)
    except Exception as e:
        logger.error("get_indicators error for %s: %s", symbol, e)
        indicators = None

    if price_data is None:
        logger.warning("broadcast: no price data for %s", symbol)
        return None

    name = price_data.get("name", symbol)
    arrow = "▲" if price_data["change"] >= 0 else "▼"
    sign = "+" if price_data["change"] >= 0 else ""
    price_line = (
        f"{name}（{symbol}）\n"
        f"現價：{price_data['price']} 元\n"
        f"漲跌：{arrow} {sign}{price_data['change']} ({sign}{price_data['change_pct']}%)"
    )

    if indicators is None:
        return price_line + "\n技術分析：資料不足，無法分析"

    news = get_stock_news(name, symbol)

    try:
        ai_block = get_ai_analysis(name, indicators, news=news, taiex=taiex_str, position=position, user_rules=user_rules)
    except Exception as e:
        logger.error("AI analysis error for %s: %s", symbol, e)
        ai_block = "技術分析：分析暫時無法使用"

    return f"{price_line}\n\n{ai_block}"


# ── FastAPI Routes ────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "bower-stock"}


@app.post("/broadcast")
async def broadcast(request: Request, authorization: str = Header(...)):
    if not BROADCAST_SECRET or authorization != f"Bearer {BROADCAST_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    users = get_all_notify_users()
    logger.info("broadcast: %d users to notify", len(users))

    # 大盤只抓一次，所有用戶共用
    taiex_data = get_taiex()
    taiex_str = format_taiex(taiex_data) if taiex_data else None

    now = datetime.now().strftime("%H:%M")
    market_line = f"【{taiex_str}】\n" if taiex_str else ""
    header = f"📈 每日收盤報告 {now}\n{market_line}"

    pushed = 0
    for user in users:
        blocks = []
        for position in user["stocks"]:
            time.sleep(0.3)
            block = build_stock_block(position, taiex_str=taiex_str, user_rules=user.get("rules"))
            if block:
                blocks.append(block)

        if not blocks:
            continue

        message = header + "\n\n".join(blocks) + "\n\n⚠️ 以上僅供個人參考，非投資建議"
        await push_message(user["user_id"], message)
        pushed += 1

    return {"status": "ok", "pushed": pushed}


@app.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: str = Header(...),
):
    body = await request.body()

    if not verify_signature(body, x_line_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()

    for event in payload.get("events", []):
        if event.get("type") != "message":
            continue
        if event["message"].get("type") != "text":
            continue

        reply_token = event["replyToken"]
        user_id = event["source"]["userId"]
        text = event["message"]["text"]
        await handle_text(reply_token, user_id, text)

    return {"status": "ok"}
