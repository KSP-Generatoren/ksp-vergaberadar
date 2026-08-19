"""Vergabe.NRW - gebuendelt ueber die cosinex-Satelliten des Landes.

Die alte Open-Data-REST-API (daten.vergabe.nrw.de, Elasticsearch) wurde
abgeschaltet; die Domain existiert nicht mehr. Der aktuelle CKAN-Datensatz
"Ausschreibungen Vergabemarktplatz NRW" auf open.nrw verweist stattdessen auf
die opendata-Endpunkte der cosinex-Portale (evergabe.nrw.de, vergabe-westfalen,
vmp-rheinland, metropoleruhr, stadt-koeln, aachen). Diese Portale deckt der
cosinex-Adapter ab - dieser Modul buendelt sie unter der Quelle "Vergabe.NRW".
"""
from __future__ import annotations

import logging

from ..models import Notice
from .cosinex import NRW_INSTANCES, fetch as cosinex_fetch

log = logging.getLogger(__name__)


def fetch(days: int = 7, **_ignored) -> list[Notice]:
    """Alle NRW-Portale. Ein einzelner Portalausfall stoppt den Lauf nicht."""
    out: list[Notice] = []
    errors: list[str] = []
    for name in NRW_INSTANCES:
        try:
            out.extend(cosinex_fetch(name))
        except Exception as exc:                      # noqa: BLE001
            log.warning("NRW/%s uebersprungen: %s", name, exc)
            errors.append(f"{name}: {exc}")
    if errors and not out:
        raise RuntimeError("; ".join(errors)[:300])
    log.info("NRW: %s Treffer aus %s Portalen", len(out), len(NRW_INSTANCES))
    return out
