"""Internes Datenmodell. Alle Quellen werden hierauf normalisiert."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import date, datetime


@dataclass
class Notice:
    # Identitaet
    source: str                      # "ted" | "doe" | "cosinex:<host>"
    source_id: str                   # Publication number oder Portal-ID
    # Inhalt
    title: str = ""
    description: str = ""
    buyer: str = ""
    buyer_city: str = ""
    nuts: str = ""
    cpv: list[str] = field(default_factory=list)
    procedure: str = ""              # VgV / UVgO / VOB-A / nichtoffen ...
    kind: str = "notice"             # notice | award | prior_information
    value_eur: float | None = None
    # Termine
    published: date | None = None
    deadline: datetime | None = None
    # Verweise
    notice_url: str = ""
    documents_url: str = ""          # eForms BT-15
    # Abgeleitet
    score: int = 0
    score_reasons: list[str] = field(default_factory=list)
    matched_product: str = ""
    kva: float | None = None
    status: str = "neu"              # neu | pruefen | angebot | abgegeben | abgelehnt | verloren | gewonnen

    @property
    def uid(self) -> str:
        return hashlib.sha1(f"{self.source}:{self.source_id}".encode()).hexdigest()[:16]

    @property
    def fulltext(self) -> str:
        return " ".join([self.title, self.description, self.buyer]).lower()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uid"] = self.uid
        for k in ("published", "deadline"):
            if d[k] is not None:
                d[k] = d[k].isoformat()
        return d


@dataclass
class DocumentSnapshot:
    """Ein Abzug der Vergabeunterlagen zu einem Zeitpunkt.

    Grundlage des Aenderungsmonitors: gleiche URL, spaeterer Zeitpunkt,
    anderer Hash -> die Vergabestelle hat nachgebessert.
    """
    notice_uid: str
    fetched_at: datetime
    files: dict[str, str]            # Dateiname -> sha256 des Inhalts
    text: str = ""

    @property
    def digest(self) -> str:
        joined = "|".join(f"{k}={v}" for k, v in sorted(self.files.items()))
        return hashlib.sha256(joined.encode()).hexdigest()[:16]
