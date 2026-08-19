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
from urllib.parse import urljoin

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
    "niedersachsen":   "https://vergabe.niedersachsen.de/Satellite",
    "brandenburg":     "https://vergabemarktplatz.brandenburg.de/VMPCenter",
    "bw":              "https://www.vergabe.landbw.de/VMPCenter",
}

# NRW laeuft vollstaendig ueber cosinex-Satelliten (die alte Open-Data-REST-API
# unter daten.vergabe.nrw.de existiert nicht mehr). Quelle der Liste: CKAN-
# Datensatz "Ausschreibungen Vergabemarktplatz NRW" auf open.nrw.
# Wird vom NRW-Adapter abgefragt, nicht von fetch_all().
NRW_INSTANCES = {
    "nrw":            "https://www.evergabe.nrw.de/VMPCenter",
    "westfalen":      "https://www.vergabe-westfalen.de/VMPSatellite",
    "rheinland":      "https://www.vmp-rheinland.de/VMPSatellite",
    "metropoleruhr":  "https://www.vergabe.metropoleruhr.de/VMPCenter",
    "koeln":          "https://vergabe.stadt-koeln.de/VMPSatellite",
    "aachen":         "https://www.vergaben-wirtschaftsregion-aachen.de/VMPSatellite",
}

LIST_PATH = "/company/announcements/categoryOverview.do"
DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2}))?")


def fetch(instance: str, cpv: str = "31127000-2", timeout: int = 45) -> list[Notice]:
    base = INSTANCES.get(instance) or NRW_INSTANCES.get(instance) or instance
    base = base.rstrip("/")
    url = f"{base}{LIST_PATH}"
    params = {"method": "showTable", "cpvCode": cpv}

    with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT},
                      follow_redirects=True) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        doc = lxml_html.fromstring(r.text)

    # Spalten der Bekanntmachungsuebersicht (Stand 2026):
    # Veroeffentlicht | Angebots-/Teilnahmefrist ("nv" = ohne) | Kurzbezeichnung
    # | Typ | Vergabeplattform/Veroeffentlicher | Aktion (Link projectForwarding)
    rows = doc.xpath("//table//tr[td]")
    out: list[Notice] = []
    for row in rows:
        cells = [" ".join(c.text_content().split()) for c in row.xpath("./td")]
        if len(cells) < 5:
            continue
        published = _parse_dt(cells[0])
        deadline = _parse_dt(cells[1])
        title, procedure, buyer = cells[2], cells[3], cells[4]
        if not title:
            continue
        link = row.xpath(".//a/@href")
        href = urljoin(f"{base}/", link[0]) if link else ""

        out.append(Notice(
            source=f"cosinex:{instance}",
            source_id=_id_from_href(href) or f"{buyer}|{title}"[:80],
            title=title,
            buyer=buyer,
            procedure=procedure,
            kind="award" if "Vergebener Auftrag" in procedure else "notice",
            # Die Uebersicht ist bereits nach diesem CPV gefiltert.
            cpv=[cpv.split("-")[0]],
            deadline=deadline,
            published=published.date() if published else None,
            notice_url=href,
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
    m = re.search(r"[?&]pid=(\d+)", href or "")
    if m:
        return m.group(1)
    m = re.search(r"/notice/([A-Z0-9]+)", href or "")
    return m.group(1) if m else ""
