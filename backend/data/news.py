"""Crypto news ingestion — multi-source, no API key required.

Tries CryptoCompare first, then CoinDesk / CoinTelegraph RSS fallbacks.
"""

from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import desc, nulls_last

from db.models import MarketNews

logger = logging.getLogger(__name__)

CRYPTOCOMPARE_URL = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
RSS_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
]
HEADERS = {
    "User-Agent": "CryptoAgent/1.0 (market-context; local-trading-bot)",
    "Accept": "application/json, application/rss+xml, application/xml, text/xml, */*",
}


def _ext_id(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:32]


async def _fetch_cryptocompare(client: httpx.AsyncClient, limit: int) -> list[dict]:
    resp = await client.get(CRYPTOCOMPARE_URL, headers=HEADERS)
    if resp.status_code == 401:
        raise RuntimeError("CryptoCompare 401")
    resp.raise_for_status()
    payload = resp.json()
    items = payload.get("Data") or []
    out = []
    for item in items[:limit]:
        ext = str(item.get("id") or item.get("guid") or "")
        if not ext:
            continue
        cats = item.get("categories") or ""
        if isinstance(cats, list):
            cats = ",".join(cats)
        currencies = ""
        raw_c = item.get("currencies") or []
        if isinstance(raw_c, list):
            currencies = ",".join(
                (c.get("code") if isinstance(c, dict) else str(c)) for c in raw_c[:8]
            )
        published = None
        if item.get("published_on"):
            try:
                published = datetime.utcfromtimestamp(int(item["published_on"]))
            except Exception:
                published = None
        source_info = item.get("source_info")
        if isinstance(source_info, dict):
            source = (source_info.get("name") or item.get("source") or "")[:100]
        else:
            source = str(item.get("source") or "")[:100]
        out.append(
            {
                "external_id": ext[:64],
                "title": (item.get("title") or "")[:500],
                "url": (item.get("url") or item.get("guid") or "")[:1000],
                "source": source,
                "categories": str(cats)[:200],
                "currencies": currencies[:200],
                "published_at": published,
            }
        )
    return out


async def _fetch_rss(client: httpx.AsyncClient, source: str, url: str, limit: int) -> list[dict]:
    resp = await client.get(url, headers=HEADERS, follow_redirects=True)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    items = root.findall("./channel/item")
    if not items:
        # Atom-ish
        ns = {"a": "http://www.w3.org/2005/Atom"}
        items = root.findall("a:entry", ns) or root.findall("entry")
    out = []
    for item in items[:limit]:
        title = (item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
        link_el = item.find("link")
        link = ""
        if link_el is not None:
            link = (link_el.get("href") or link_el.text or "").strip()
        if not link:
            link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link or title)[:200]
        pub = item.findtext("pubDate") or item.findtext("{http://www.w3.org/2005/Atom}updated")
        published = None
        if pub:
            try:
                published = parsedate_to_datetime(pub)
                if published.tzinfo:
                    published = published.replace(tzinfo=None)
            except Exception:
                published = None
        cats = [c.text for c in item.findall("category") if c.text]
        if not title:
            continue
        out.append(
            {
                "external_id": _ext_id(f"{source}:{guid}")[:64],
                "title": title[:500],
                "url": link[:1000],
                "source": source[:100],
                "categories": ",".join(cats)[:200],
                "currencies": "",
                "published_at": published,
            }
        )
    return out


async def store_market_news(db: Session, limit: int = 40) -> int:
    """Fetch latest headlines and upsert by external_id. Returns new rows count."""
    added = 0
    rows: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            try:
                rows = await _fetch_cryptocompare(client, limit)
            except Exception as e:
                logger.info("CryptoCompare news unavailable (%s) — using RSS fallbacks", e)
                for source, url in RSS_FEEDS:
                    try:
                        rows.extend(await _fetch_rss(client, source, url, max(10, limit // 2)))
                    except Exception as rss_err:
                        logger.warning("RSS %s failed: %s", source, rss_err)
                rows = rows[:limit]

        for row in rows:
            exists = db.query(MarketNews.id).filter(MarketNews.external_id == row["external_id"]).first()
            if exists:
                continue
            db.add(MarketNews(**row))
            added += 1
        if added:
            db.commit()
            logger.info("Stored %d news headlines", added)
        return added
    except Exception as e:
        logger.warning("News fetch failed: %s", e)
        db.rollback()
        return 0


def recent_news_for_context(db: Session, limit: int = 8) -> list[dict]:
    rows = (
        db.query(MarketNews)
        .order_by(nulls_last(desc(MarketNews.published_at)), desc(MarketNews.created_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "title": r.title,
            "source": r.source,
            "currencies": r.currencies,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "url": r.url,
        }
        for r in rows
    ]
