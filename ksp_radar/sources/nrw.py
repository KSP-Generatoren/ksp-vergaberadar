"""Vergabe.NRW Open-Data-Schnittstelle.

Vollstaendig dokumentiert ueber open.nrw. Elasticsearch-Syntax, JSON,
Delta-Abfragen - der sauberste Laender-Zugang, den es gibt. Vorlage fuer
weitere Bundeslaender.
"""
from __future__ import annotations

import logging

import httpx

from ..config import USER_AGENT
from ..models import Notice

log = logging.getLogger(__name__)
BASE = "https://daten.vergabe.nrw.de/rest/evergabe"


def fetch(query: str = "Netzersatzanlage OR Notstromaggregat OR Stromerzeuger",
          days: int = 7, size: int = 100) -> list[Notice]:
    params = {
        "q": query,
        "size": size,
        "page": 1,
        "range_must[CREATED_AT][gte]": f"now-{days}d/d",
        "sort[CREATED_AT]": "DESC",
    }
    out: list[Notice] = []
    with httpx.Client(timeout=45, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json",
    }) as client:
        while True:
            r = client.get(BASE, params=params)
            r.raise_for_status()
            data = r.json()
            hits = data.get("hits", data.get("results", []))
            if not hits:
                break
            for h in hits:
                src = h.get("_source", h)
                out.append(Notice(
                    source="nrw",
                    source_id=str(h.get("_id") or src.get("ID", "")),
                    title=src.get("TITLE", ""),
                    description=src.get("DESCRIPTION", ""),
                    buyer=src.get("AUTHORITY", ""),
                    buyer_city=src.get("CITY", ""),
                    cpv=[str(c) for c in (src.get("CPV_CODES") or [])],
                    procedure=src.get("PROCEDURE_TYPE", ""),
                    notice_url=src.get("URL", ""),
                    documents_url=src.get("DOCUMENTS_URL", ""),
                ))
            if len(hits) < size:
                break
            params["page"] += 1
    log.info("NRW: %s Treffer", len(out))
    return out
