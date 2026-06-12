import hashlib
import hmac
import logging
import os

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

from stock import format_stock_message, get_stock_price

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Bower Stock")

LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"


# ── LINE Webhook ──────────────────────────────────────────────────────────────

def verify_signature(body: bytes, signature: str) -> bool:
    import base64
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

async def handle_text(reply_token: str, text: str) -> None:
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

    else:
        await reply_message(
            reply_token,
            "Bower Stock 指令列表：\n"
            "/查股 [代號] — 查詢股票現價\n"
            "\n更多功能即將推出 🚀",
        )


# ── FastAPI Routes ────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "service": "bower-stock"}


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
        text = event["message"]["text"]
        await handle_text(reply_token, text)

    return {"status": "ok"}
