"""Konfiguration: Was KSP verkauft, und woran man passende Ausschreibungen erkennt.

Alles, was fachlich ist, steht hier. Der Rest des Codes ist generisch.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

CONTACT = os.getenv("RADAR_CONTACT", "info@qp-germany.com")
USER_AGENT = f"KSP-Vergaberadar/1.0 (+{CONTACT})"
DB_PATH = os.getenv("RADAR_DB", "./data/radar.sqlite3")

# --------------------------------------------------------------------------
# CPV-Allowlist. Kernkategorie zuerst; die weiten Codes fangen Ausschreibungen,
# die die Vergabestelle zu grob klassifiziert hat.
# --------------------------------------------------------------------------
CPV_CORE = {
    "31127000": "Notstromaggregat",
    "31121000": "Generatoraggregate",
    "31121100": "Generatoraggregate mit Selbstzuendungsmotor",
    "31122000": "Generatorenanlagen",
    "31120000": "Generatoren",
    "31682500": "Notstromausruestung",
}
CPV_WIDE = {
    "31682510": "Notstromanlagen",
    "45315300": "Stromversorgungsanlagen",
    "50532000": "Reparatur/Wartung elektrischer Maschinen",
    "09134200": "Dieselkraftstoff",
    "34223300": "Anhaenger",
}

# --------------------------------------------------------------------------
# Volltext-Layer. CPV wird von Vergabestellen regelmaessig falsch oder zu grob
# gesetzt - deshalb wird nie nur nach CPV gefiltert.
# --------------------------------------------------------------------------
KEYWORDS_STRONG = [
    "netzersatzanlage", "netzersatzanlagen", "nea", "fwa-nea",
    "notstromaggregat", "notstromaggregate", "notstromanlage",
    "stromerzeuger", "stromerzeugungsaggregat", "stromaggregat",
    "din 14685", "anhaengeraggregat", "aggregatanhaenger",
]
KEYWORDS_WEAK = [
    "notstrom", "netzersatz", "eigenstromversorgung", "ersatzstromversorgung",
    "notstromversorgung", "kritis", "notfallinformationspunkt", "leuchtturm",
    "blackout", "stromausfall",
]
# Trifft ein Negativbegriff und kein starker Begriff, faellt der Datensatz raus.
KEYWORDS_NEGATIVE = [
    "blockheizkraftwerk", "bhkw", "photovoltaik", "pv-anlage", "windkraft",
    "windenergie", "batteriespeicher", "usv-anlage",
    "kernkraft", "wasserkraft", "biogas",
]
# Begriffe, die auch zusammen mit einem Kernbegriff ausschliessen:
# Zubehoer und Pruefmittel, die wir nicht liefern.
KEYWORDS_EXCLUDE_HARD = [
    "lastbank", "belastungswiderstand", "pruefstand", "prüfstand",
    "lastwiderstand", "load bank",
]

# --------------------------------------------------------------------------
# Produktprofil. Grundlage fuer das Matching und fuer das KI-Dossier.
# Werte aus dem KSP-50Y Datenblatt (Stand Angebot AG2026/06KS0617).
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Product:
    name: str
    kva_min: float
    kva_max: float
    bauform: str
    merkmale: list[str] = field(default_factory=list)

PORTFOLIO = [
    Product(
        name="KSP-50Y Stage V (Anhaenger)",
        kva_min=40, kva_max=60, bauform="mobil/Anhaenger",
        merkmale=[
            "YTO-Motor, EU-Typgenehmigung Stage V",
            "Schalldruckpegel 65 dB(A) in 7 m",
            "200 L Tank, 7,8 L/h bei 75 % Last -> ca. 25 h Laufzeit",
            "Leroy Somer Generator, ComAp Steuerung, BENDER Isolationsueberwachung",
            "Aluminiumgehaeuse, abschliessbarer Stauraum",
            "5 CEE-Dosen (125 A / 63 A), je eigener Schutzschalter + Hauptschalter",
            "NATO-Dose, BOS-Beleuchtung",
            "Anhaengerzulassung, AdBlue-Erstbefuellung",
        ],
    ),
    Product(
        name="KSP mobil 20-40 kVA",
        kva_min=15, kva_max=40, bauform="mobil/Anhaenger",
        merkmale=["Stage V", "Anhaenger- oder Kufenausfuehrung"],
    ),
    Product(
        name="KSP mobil 60-200 kVA",
        kva_min=60, kva_max=200, bauform="mobil/Anhaenger",
        merkmale=["Stage V", "Anhaenger- oder Containerausfuehrung"],
    ),
]

# Ausserhalb dieses Bandes wird es unattraktiv: zu klein lohnt nicht,
# zu gross faellt aus dem Portfolio.
KVA_SWEET_SPOT = (20.0, 200.0)
KVA_HARD_LIMIT = (10.0, 400.0)

PROFILE_TEXT = """
KSP Generatoren (QP International GmbH, Wuerzburg) liefert mobile und stationaere
Netzersatzanlagen von 20 bis 200 kVA an Kommunen, Feuerwehren, THW, Bundeswehr,
Polizei, Stadtwerke, Wasserversorger und KRITIS-Betreiber. Schwerpunkt sind
Anhaengeraggregate nach DIN 14685 fuer den Bevoelkerungsschutz sowie mobile
Netzersatzanlagen zur Absicherung von Notfallinformationspunkten und Leuchttuermen.
Geliefert werden Diesel-Aggregate der Abgasstufe Stage V inklusive Zulassung,
Inbetriebnahme, DGUV-V3-Erstpruefung, Einweisung und Wartungsvertrag.
Nicht im Portfolio: Blockheizkraftwerke, Photovoltaik, Batteriespeicher,
reine Bauleistungen und reine Wartungsvertraege ohne Lieferanteil.
""".strip()

# --------------------------------------------------------------------------
# Go/No-Go-Schwellen
# --------------------------------------------------------------------------
SCORE_GO = 70          # ab hier: pruefen und in der Regel anbieten
SCORE_WATCH = 45       # dazwischen: manuell ansehen
# darunter: automatisch ablegen

# --------------------------------------------------------------------------
# Overrides: Der Profil-Editor der Weboberflaeche exportiert eine JSON-Datei.
# Liegt sie unter data/profile_override.json im Repo, gewinnt sie gegen die
# Werte oben - so aendert man das Suchprofil ohne Code.
# --------------------------------------------------------------------------
def _apply_overrides() -> None:
    import json
    import pathlib
    f = pathlib.Path(__file__).resolve().parent.parent / "data" / "profile_override.json"
    if not f.exists():
        return
    try:
        o = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    g = globals()
    for key in ("KEYWORDS_STRONG", "KEYWORDS_WEAK", "KEYWORDS_NEGATIVE",
                "KEYWORDS_EXCLUDE_HARD", "PROFILE_TEXT"):
        if key.lower() in o:
            g[key] = o[key.lower()]
    if "cpv_core" in o:
        g["CPV_CORE"] = dict(o["cpv_core"])
    if "kva_sweet_spot" in o and len(o["kva_sweet_spot"]) == 2:
        g["KVA_SWEET_SPOT"] = tuple(float(x) for x in o["kva_sweet_spot"])
    if "score_go" in o:
        g["SCORE_GO"] = int(o["score_go"])
    if "score_watch" in o:
        g["SCORE_WATCH"] = int(o["score_watch"])


_apply_overrides()
