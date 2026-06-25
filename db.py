import os
from datetime import datetime

from google.cloud import firestore

_db = None


def get_db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=os.environ["GCP_PROJECT_ID"], database="stockdb")
    return _db


def _user_ref(user_id: str):
    return get_db().collection("stock_users").document(user_id)


# ── 追蹤清單 ──────────────────────────────────────────────────────────────────
# stocks 結構：[{"symbol": "2330", "cost": 2350.0, "date": "2026-06-25", "qty": 1000}, ...]
# cost 為 None 時代表「觀察中」，尚未持有

def _normalize_stocks(stocks: list) -> list[dict]:
    """相容舊版純代號字串格式"""
    return [
        {"symbol": s, "cost": None, "qty": None, "date": None} if isinstance(s, str) else s
        for s in stocks
    ]


def add_stock(user_id: str, symbol: str, cost: float | None = None, qty: float | None = None) -> bool:
    """加入追蹤，最多 10 支。回傳 False 表示已達上限。已存在則更新成本/股數。"""
    ref = _user_ref(user_id)
    doc = ref.get()
    stocks = _normalize_stocks(doc.to_dict().get("stocks", []) if doc.exists else [])

    existing = next((s for s in stocks if s["symbol"] == symbol), None)
    if existing:
        existing["cost"] = cost
        existing["qty"] = qty
        existing["date"] = datetime.now().strftime("%Y-%m-%d")
        ref.set({"stocks": stocks, "notify": True}, merge=True)
        return True

    if len(stocks) >= 10:
        return False

    stocks.append({
        "symbol": symbol,
        "cost": cost,
        "qty": qty,
        "date": datetime.now().strftime("%Y-%m-%d"),
    })
    ref.set({"stocks": stocks, "notify": True}, merge=True)
    return True


def remove_stock(user_id: str, symbol: str) -> bool:
    """移除追蹤。回傳 False 表示原本不在清單。"""
    ref = _user_ref(user_id)
    doc = ref.get()
    if not doc.exists:
        return False

    stocks = _normalize_stocks(doc.to_dict().get("stocks", []))
    new_stocks = [s for s in stocks if s["symbol"] != symbol]
    if len(new_stocks) == len(stocks):
        return False

    ref.set({"stocks": new_stocks}, merge=True)
    return True


def get_stocks(user_id: str) -> list[dict]:
    """回傳持股清單，每筆含 symbol/cost/qty/date（相容舊版純代號字串格式）"""
    doc = _user_ref(user_id).get()
    if not doc.exists:
        return []
    stocks = doc.to_dict().get("stocks", [])
    return [
        {"symbol": s, "cost": None, "qty": None, "date": None} if isinstance(s, str) else s
        for s in stocks
    ]


def get_symbols(user_id: str) -> list[str]:
    """僅回傳股票代號清單"""
    return [s["symbol"] for s in get_stocks(user_id)]


# ── 推播開關 ──────────────────────────────────────────────────────────────────

def set_notify(user_id: str, enabled: bool) -> None:
    _user_ref(user_id).set({"notify": enabled}, merge=True)


def get_notify(user_id: str) -> bool:
    doc = _user_ref(user_id).get()
    if not doc.exists:
        return True
    return doc.to_dict().get("notify", True)


def get_all_notify_users() -> list[dict]:
    """回傳所有 notify=True 且有追蹤股票的用戶，含 user_id 與 stocks 清單"""
    docs = get_db().collection("stock_users").where("notify", "==", True).stream()
    result = []
    for doc in docs:
        data = doc.to_dict()
        stocks = data.get("stocks", [])
        if stocks:
            result.append({"user_id": doc.id, "stocks": stocks})
    return result
