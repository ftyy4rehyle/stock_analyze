import os

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

def add_stock(user_id: str, symbol: str) -> bool:
    """加入追蹤，最多 10 支。回傳 False 表示已達上限。"""
    ref = _user_ref(user_id)
    doc = ref.get()
    stocks = doc.to_dict().get("stocks", []) if doc.exists else []

    if symbol in stocks:
        return True
    if len(stocks) >= 10:
        return False

    stocks.append(symbol)
    ref.set({"stocks": stocks, "notify": True}, merge=True)
    return True


def remove_stock(user_id: str, symbol: str) -> bool:
    """移除追蹤。回傳 False 表示原本不在清單。"""
    ref = _user_ref(user_id)
    doc = ref.get()
    if not doc.exists:
        return False

    stocks = doc.to_dict().get("stocks", [])
    if symbol not in stocks:
        return False

    stocks.remove(symbol)
    ref.set({"stocks": stocks}, merge=True)
    return True


def get_stocks(user_id: str) -> list[str]:
    doc = _user_ref(user_id).get()
    if not doc.exists:
        return []
    return doc.to_dict().get("stocks", [])


# ── 推播開關 ──────────────────────────────────────────────────────────────────

def set_notify(user_id: str, enabled: bool) -> None:
    _user_ref(user_id).set({"notify": enabled}, merge=True)


def get_notify(user_id: str) -> bool:
    doc = _user_ref(user_id).get()
    if not doc.exists:
        return True
    return doc.to_dict().get("notify", True)
