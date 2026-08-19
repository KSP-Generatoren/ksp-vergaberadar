"""Ein Adapter fuer dutzende Portale.

Der Hebel des ganzen Projekts: Die ~800 deutschen Vergabequellen laufen auf
einer Handvoll Softwareprodukte. cosinex allein betreibt DTVP, eVergabe-Online
des Bundes und die meisten Laender-Vergabemarktplaetze. Die Instanzen
unterscheiden sich in der Domain, nicht im Aufbau - ein Adapter genuegt.

Die Bekanntmachungsuebersicht ist oeffentlich und ohne Anmeldung erreichbar,
weil Vergabestellen ihre Bekanntmachungen auf der eigenen Website einbinden
sollen. Genau dafuer ist sie gedacht.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx
from lxml import html as lxml_html

from ..config import USER_AGENT
from ..models import Notice

log = logging.getLogger(__name__)

# Bekannte cosinex-VMP-Instanzen. Die Liste ist erweiterbar, ohne dass Code
# geaendert werden muss.
INSTANCES = {
    "dtvp":            "https://www.dtvp.de/Satellite",
    "evergabe-online": "https://www.evergabe-online.de/Satellite",
    "nrw":             "https://www.evergabe.nrw.de/VMPCenter",
    "niedersachsen":   "https://vergabe.niedersachsen.de/Satellite",
    "brandenburg":     "https://vergabemarktplatz.brandenburg.de/VMPCenter",
    "rheinland":       "https://www.vmp-rheinland.de/VMPSatellite",
    "metropoleruhr":   "https://www.vergabe.metropoleruhr.de/VMPCenter",
    "bw":              "https://www.vergabe.landbw.de/VMPCenter",
}

LIST_PATH = "/company/announcements/categoryOverview.do"
DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2}))?")


def fetch(instance: str, cpv: str = "31127000-2", timeout: int = 45) -> list[Notice]:
    base = INSTANCES.get(instance, instance).rstrip("/")
    url = f"{base}{LIST_PATH}"
    params = {"method": "showTable", "cpvCode": cpv}

    with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT},
                      follow_redirects=True) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        doc = lxml_html.fromstring(r.text)

    rows = doc.xpath("//table//tr[td]")
    out: list[Notice] = []
    for row in rows:
        cells = [" ".join(c.text_content().split()) for c in row.xpath("./td")]
        if len(cells) < 3:
            continue
        link = row.xpath(".//a/@href")
        href = link[0] if link else ""
        if href and not href.startswith("http"):
            href = f"{base}/{href.lstrip('/')}"

        buyer, title = cells[0], cells[1]
        procedure = cells[2] if len(cells) > 2 else ""
        deadline = _parse_dt(cells[3]) if len(cells) > 3 else None
        published = _parse_dt(cells[4]) if len(cells) > 4 else None

        out.append(Notice(
            source=f"cosinex:{instance}",
            source_id=_id_from_href(href) or f"{buyer}|{title}",
            title=title,
            buyer=buyer,
            procedure=procedure,
            kind="award" if "Vergebener Auftrag" in procedure else "notice",
            deadline=deadline,
            published=published.date() if published else None,
            notice_url=href,
            documents_url=f"{href.rstrip('/')}/documents" if href else "",
        ))

    log.info("cosinex/%s: %s Eintraege fuer CPV %s", instance, len(out), cpv)
    return out


def fetch_all(cpv: str = "31127000-2") -> list[Notice]:
    """Alle bekannten Instanzen. Fehler einer Instanz stoppen den Lauf nicht."""
    out: list[Notice] = []
    for name in INSTANCES:
        try:
            out.extend(fetch(name, cpv))
        except Exception as exc:                      # noqa: BLE001
            log.warning("cosinex/%s uebersprungen: %s", name, exc)
    return out


def _parse_dt(text: str) -> datetime | None:
    m = DATE_RE.search(text or "")
    if not m:
        return None
    d, mo, y, h, mi = m.groups()
    return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0))


def _id_from_href(href: str) -> str:
    m = re.search(r"/notice/([A-Z0-9]+)", href or "")
    return m.group(1) if m else ""
