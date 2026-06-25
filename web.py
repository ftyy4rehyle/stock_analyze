import logging
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer

from chart import get_chart_data
from db import add_stock, get_stocks, remove_stock
from stock import get_stock_price

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

LINE_LOGIN_CHANNEL_ID = os.environ["LINE_LOGIN_CHANNEL_ID"]
LINE_LOGIN_CHANNEL_SECRET = os.environ["LINE_LOGIN_CHANNEL_SECRET"]
BASE_URL = os.environ["BASE_URL"]  # e.g. https://bower-stock-xxx.a.run.app
SESSION_SECRET = os.environ["SESSION_SECRET"]

_signer = URLSafeSerializer(SESSION_SECRET, salt="session")

LINE_AUTH_URL = "https://access.line.me/oauth2/v2.1/authorize"
LINE_TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
LINE_PROFILE_URL = "https://api.line.me/v2/profile"


# ── Session helpers ───────────────────────────────────────────────────────────

def _make_session(user_id: str, display_name: str) -> str:
    return _signer.dumps({"user_id": user_id, "display_name": display_name})


def _parse_session(cookie: str | None) -> dict | None:
    if not cookie:
        return None
    try:
        return _signer.loads(cookie)
    except BadSignature:
        return None


# ── Auth routes ───────────────────────────────────────────────────────────────

@router.get("/auth/login")
def login():
    state = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": LINE_LOGIN_CHANNEL_ID,
        "redirect_uri": f"{BASE_URL}/auth/callback",
        "state": state,
        "scope": "profile",
    }
    response = RedirectResponse(f"{LINE_AUTH_URL}?{urlencode(params)}")
    response.set_cookie("oauth_state", state, httponly=True, max_age=600)
    return response


@router.get("/auth/callback")
async def callback(code: str, state: str, request: Request):
    saved_state = request.cookies.get("oauth_state")
    if not saved_state or saved_state != state:
        raise HTTPException(status_code=400, detail="Invalid state")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(LINE_TOKEN_URL, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"{BASE_URL}/auth/callback",
            "client_id": LINE_LOGIN_CHANNEL_ID,
            "client_secret": LINE_LOGIN_CHANNEL_SECRET,
        })
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="取得 Token 失敗")

        profile_resp = await client.get(
            LINE_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        profile = profile_resp.json()

    user_id = profile.get("userId")
    display_name = profile.get("displayName", "使用者")
    if not user_id:
        raise HTTPException(status_code=400, detail="取得用戶資料失敗")

    response = RedirectResponse("/")
    response.set_cookie(
        "session",
        _make_session(user_id, display_name),
        httponly=True,
        max_age=86400 * 30,
        secure=True,
        samesite="lax",
    )
    response.delete_cookie("oauth_state")
    return response


@router.get("/auth/logout")
def logout():
    response = RedirectResponse("/")
    response.delete_cookie("session")
    return response


# ── Web pages ─────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def index(request: Request, session: str | None = Cookie(default=None)):
    user = _parse_session(session)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request})
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "display_name": user["display_name"],
    })


# ── API ───────────────────────────────────────────────────────────────────────

@router.get("/api/stocks")
def api_get_stocks(session: str | None = Cookie(default=None)):
    user = _parse_session(session)
    if not user:
        raise HTTPException(status_code=401)
    stocks = get_stocks(user["user_id"])
    result = []
    for s in stocks:
        symbol = s["symbol"]
        price_data = get_stock_price(symbol)
        gain_pct = None
        if s.get("cost") and price_data:
            gain_pct = round((price_data["price"] - s["cost"]) / s["cost"] * 100, 2)
        result.append({
            "symbol": symbol,
            "name": price_data["name"] if price_data else symbol,
            "price": price_data["price"] if price_data else None,
            "change": price_data["change"] if price_data else None,
            "change_pct": price_data["change_pct"] if price_data else None,
            "cost": s.get("cost"),
            "qty": s.get("qty"),
            "gain_pct": gain_pct,
        })
    return result


@router.post("/api/stocks/{symbol}")
def api_add_stock(
    symbol: str,
    cost: float | None = None,
    qty: float | None = None,
    session: str | None = Cookie(default=None),
):
    user = _parse_session(session)
    if not user:
        raise HTTPException(status_code=401)
    ok = add_stock(user["user_id"], symbol.strip().upper(), cost=cost, qty=qty)
    if not ok:
        raise HTTPException(status_code=400, detail="追蹤清單已達上限（最多 10 支）")
    return {"ok": True}


@router.delete("/api/stocks/{symbol}")
def api_remove_stock(symbol: str, session: str | None = Cookie(default=None)):
    user = _parse_session(session)
    if not user:
        raise HTTPException(status_code=401)
    remove_stock(user["user_id"], symbol.strip().upper())
    return {"ok": True}


@router.get("/api/chart/{symbol}")
def api_chart(symbol: str, session: str | None = Cookie(default=None)):
    user = _parse_session(session)
    if not user:
        raise HTTPException(status_code=401)
    data = get_chart_data(symbol.strip().upper())
    if not data:
        raise HTTPException(status_code=404, detail="查無資料")
    return data
