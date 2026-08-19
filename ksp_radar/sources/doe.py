"""Datenservice Oeffentlicher Einkauf (Bund) - oeffentlichevergabe.de

Die wichtigste deutsche Quelle: liefert als einzige zentrale Stelle auch
UNTERSCHWELLIGE Bekanntmachungen strukturiert (eForms:DE), und genau dort
liegt der Grossteil des KSP-Geschaefts.

Betreiber: Beschaffungsamt des BMI.
Die Open-Data-Schnittstelle ist dokumentiert unter bescha.bund.de; die
Basis-URL wird bewusst konfigurierbar gehalten, weil sie sich mit dem
Ausbau des Dienstes noch aendert.
"""
from __future__ import annotations

import io
import logging
import os
import zipfile
from datetime import date, datetime, timedelta

import httpx
from lxml import etree

from ..config import CPV_CORE, CPV_WIDE, KEYWORDS_STRONG, KEYWORDS_WEAK, USER_AGENT
from ..models import Notice

log = logging.getLogger(__name__)

BASE = os.getenv("DOE_API_BASE", "https://oeffentlichevergabe.de/api/notice-exports")

NS = {
    "cn": "urn:oasis:names:specification:ubl:schema:xsd:ContractNotice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "efac": "http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1",
    "efbc": "http://data.europa.eu/p27/eforms-ubl-extension-basic-components/1",
}


def fetch(days: int = 7) -> list[Notice]:
    """Holt die Bekanntmachungen der letzten N Tage.

    Die API liefert je Kalendertag (pubDay) ein ZIP mit einer eForms-XML pro
    Bekanntmachung. Der aktuelle Tag ist nicht abrufbar (400), deshalb beginnt
    die Schleife bei gestern. Zurueckgegeben wird nur, was per CPV oder
    Schluesselbegriff zum Profil passt - der Dienst publiziert bundesweit
    ~1000 Bekanntmachungen pro Tag, das meiste davon fachfremd.
    """
    out: list[Notice] = []
    total = 0

    with httpx.Client(timeout=120, headers={"User-Agent": USER_AGENT},
                      follow_redirects=True) as client:
        for back in range(1, days + 1):
            day = date.today() - timedelta(days=back)
            r = client.get(BASE, params={"pubDay": day.isoformat(),
                                         "format": "eforms.zip"})
            if r.status_code == 400:
                log.warning("DOE: pubDay %s nicht abrufbar (400)", day)
                continue
            r.raise_for_status()
            try:
                zf = zipfile.ZipFile(io.BytesIO(r.content))
            except zipfile.BadZipFile:
                log.warning("DOE: pubDay %s lieferte kein ZIP", day)
                continue
            for name in zf.namelist():
                if not name.endswith(".xml"):
                    continue
                total += 1
                n = parse_eforms(zf.read(name))
                if n and _relevant(n):
                    out.append(n)

    log.info("DOE: %s Bekanntmachungen geprueft, %s zum Profil passend", total, len(out))
    return out


def _cpv_hit(n: Notice) -> bool:
    allow = set(CPV_CORE) | set(CPV_WIDE)
    return any(c[:8] in allow for c in n.cpv)


def _relevant(n: Notice) -> bool:
    """CPV-Treffer oder Schluesselbegriff im Text - nie nur CPV."""
    if _cpv_hit(n):
        return True
    text = f"{n.title} {n.description}".lower()
    return any(k in text for k in KEYWORDS_STRONG) or any(k in text for k in KEYWORDS_WEAK)


def parse_eforms(xml: bytes) -> Notice | None:
    """eForms:DE / eForms:EU -> Notice.

    Nur die Felder, die fuer die Bewertung gebraucht werden. Der eForms-
    Datensatz hat ueber 300 Business Terms; die meisten sind fuer einen
    Bieter ohne Belang.
    """
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError:
        return None

    def t(xpath: str) -> str:
        el = root.xpath(xpath, namespaces=NS)
        if not el:
            return ""
        v = el[0]
        return (v.text or "").strip() if hasattr(v, "text") else str(v).strip()

    def tl(xpath: str) -> list[str]:
        return [(e.text or "").strip() for e in root.xpath(xpath, namespaces=NS)]

    pub = t("//cbc:ID[@schemeName='notice-id']") or t("//cbc:ID")
    if not pub:
        return None

    published = None
    raw_date = t("//cbc:IssueDate")
    if raw_date:
        try:
            published = datetime.fromisoformat(raw_date[:10]).date()
        except ValueError:
            pass

    deadline = None
    d_date = t("//cac:TenderSubmissionDeadlinePeriod/cbc:EndDate")
    d_time = t("//cac:TenderSubmissionDeadlinePeriod/cbc:EndTime")
    if d_date:
        try:
            deadline = datetime.fromisoformat(f"{d_date[:10]}T{(d_time or '00:00:00')[:8]}")
        except ValueError:
            pass

    value = None
    raw_value = t("//cbc:EstimatedOverallContractAmount")
    if raw_value:
        try:
            value = float(raw_value)
        except ValueError:
            pass

    return Notice(
        source="doe",
        source_id=pub,
        title=t("//cac:ProcurementProject/cbc:Name"),
        description=t("//cac:ProcurementProject/cbc:Description"),
        buyer=t("//cac:ContractingParty//cbc:RegistrationName")
        or t("//cac:PartyName/cbc:Name"),
        buyer_city=t("//cac:ContractingParty//cbc:CityName")
        or t("//cac:PostalAddress/cbc:CityName"),
        nuts=t("//cac:RealizedLocation//cbc:ID"),
        cpv=tl("//cac:MainCommodityClassification/cbc:ItemClassificationCode")
        + tl("//cac:AdditionalCommodityClassification/cbc:ItemClassificationCode"),
        procedure=t("//cac:TenderingProcess/cbc:ProcedureCode"),
        value_eur=value,
        published=published,
        deadline=deadline,
        notice_url=f"https://oeffentlichevergabe.de/ui/de/search/details?noticeId={pub}",
        # BT-15: Adresse der Vergabeunterlagen
        documents_url=t("//cac:CallForTendersDocumentReference//cbc:URI")
        or t("//cbc:AccessToolsURI"),
    )
