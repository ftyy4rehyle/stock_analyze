import logging
import xml.etree.ElementTree as ET
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


def get_stock_news(name: str, symbol: str, max_items: int = 3) -> list[str]:
    """抓 Google News RSS，回傳最新 N 則新聞標題"""
    query = quote(f"{name} {symbol}")
    url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        resp = httpx.get(url, timeout=8, follow_redirects=True)
        root = ET.fromstring(resp.text)
        titles = []
        for item in root.findall(".//item")[:max_items]:
            title = item.findtext("title", "").strip()
            if title:
                # 移除來源後綴，例如「 - 經濟日報」
                title = title.rsplit(" - ", 1)[0].strip()
                titles.append(title)
        return titles
    except Exception as e:
        logger.warning("get_stock_news error [%s]: %s", symbol, e)
        return []
