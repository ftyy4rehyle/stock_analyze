import logging
import time

import httpx

logger = logging.getLogger(__name__)


def get_json(url: str, params: dict, retries: int = 2, delay: float = 1.0) -> dict | None:
    """對 TWSE/TPEx 發請求，失敗（含限流空白回應）時重試"""
    last_error = None
    for attempt in range(retries):
        try:
            resp = httpx.get(url, params=params, timeout=10, follow_redirects=True)
            return resp.json()
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(delay)
    logger.warning("get_json failed after %d retries [%s]: %s", retries, url, last_error)
    return None
