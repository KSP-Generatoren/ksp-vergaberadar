"""TED Search API v3 - EU-weite Bekanntmachungen.

Endpoint:  POST https://api.ted.europa.eu/v3/notices/search
Auth:      keine
Fair Use:  700 Requests/Minute, 600 Downloads je 6 Minuten pro IP
Doku:      https://docs.ted.europa.eu/api/latest/search.html
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import httpx

from ..config import CPV_CORE, CPV_WIDE, USER_AGENT
from ..models import Notice

log = logging.getLogger(__name__)
API = "https://api.ted.europa.eu/v3/notices/search"

# Felder, die die Search API zurueckgeben soll.
FIELDS = [
    "publication-number", "notice-title", "buyer-name", "buyer-city",
    "place-of-performance", "classification-cpv", "notice-type",
    "publication-date", "deadline-receipt-request", "description-lot",
    "procedure-type", "total-value", "links",
]


def _query(cpvs: list[str], days: int, country: str = "DEU") -> str:
    """TED Expert Query.

    CPV ist hierarchisch: 31127000 trifft auch Unterknoten.
    publication-date verlangt YYYYMMDD oder today(-N) - kein ISO-Datum.
    """
    cpv_expr = " OR ".join(f"classification-cpv={c}" for c in cpvs)
    return (
        f"({cpv_expr}) "
        f"AND place-of-performance IN ({country}) "
        f"AND publication-date >= today(-{days})"
    )


def fetch(days: int = 7, include_wide: bool = True, page_size: int = 100) -> list[Notice]:
    cpvs = list(CPV_CORE) + (list(CPV_WIDE) if include_wide else [])
    since = date.today() - timedelta(days=days)
    out: list[Notice] = []
    page = 1

    with httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT}) as client:
        while True:
            payload = {
                "query": _query(cpvs, days),
                "fields": FIELDS,
                "page": page,
                "limit": page_size,
                "scope": "ACTIVE",
            }
            r = client.post(API, json=payload)
            if r.status_code == 429:
                log.warning("TED rate limit erreicht - Abbruch bei Seite %s", page)
                break
            r.raise_for_status()
            data = r.json()
            batch = data.get("notices", []) or data.get("results", [])
            if not batch:
                break
            out.extend(_to_notice(n) for n in batch)
            total = data.get("totalNoticeCount", 0)
            if page * page_size >= total:
                break
            page += 1

    log.info("TED: %s Bekanntmachungen seit %s", len(out), since)
    return out


def _first(value):
    """TED liefert viele Felder mehrsprachig als dict oder als Liste."""
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("deu", "ger", "de", "eng", "en"):
            if key in value:
                return _first(value[key])
        return _first(next(iter(value.values()), ""))
    if isinstance(value, list):
        return _first(value[0]) if value else ""
    return str(value)


def _parse_dt(value: str) -> datetime | None:
    """TED liefert Daten mit Offset, teils ohne Uhrzeit: '2026-08-05+02:00'.

    Der Offset ist Berliner Ortszeit; er wird verworfen, die Wandzeit bleibt.
    """
    s = (value or "").strip().replace("Z", "+00:00")
    for cand in (s, s[:19], s[:10]):
        if not cand:
            continue
        try:
            return datetime.fromisoformat(cand).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def _to_notice(raw: dict) -> Notice:
    pub = _first(raw.get("publication-number"))
    cpv = raw.get("classification-cpv") or []
    if isinstance(cpv, (str, dict)):
        cpv = [cpv]

    published_dt = _parse_dt(_first(raw.get("publication-date")))
    published = published_dt.date() if published_dt else None

    deadline = _parse_dt(_first(raw.get("deadline-receipt-request")))

    value = None
    try:
        value = float(_first(raw.get("total-value")) or 0) or None
    except (TypeError, ValueError):
        pass

    return Notice(
        source="ted",
        source_id=pub,
        title=_first(raw.get("notice-title")),
        description=_first(raw.get("description-lot")),
        buyer=_first(raw.get("buyer-name")),
        buyer_city=_first(raw.get("buyer-city")),
        nuts=_first(raw.get("place-of-performance")),
        cpv=[_first(c) for c in cpv],
        procedure=_first(raw.get("procedure-type")),
        kind=_first(raw.get("notice-type")) or "notice",
        value_eur=value,
        published=published,
        deadline=deadline,
        notice_url=f"https://ted.europa.eu/de/notice/-/detail/{pub}",
        documents_url=_extract_documents_url(raw),
    )


def _extract_documents_url(raw: dict) -> str:
    """eForms BT-15 'Documents URL'.

    Nach Paragraf 41 VgV bzw. Paragraf 29 UVgO muessen die Vergabeunterlagen
    unter dieser Adresse unentgeltlich, uneingeschraenkt, vollstaendig und
    direkt - also ohne Registrierung - abrufbar sein.
    """
    links = raw.get("links") or {}
    for key in ("documents", "BT-15", "documentsUrl"):
        if key in links:
            return _first(links[key])
    return ""
