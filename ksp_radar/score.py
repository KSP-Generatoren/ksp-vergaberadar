"""Relevanzbewertung.

Drei Schichten, absichtlich in dieser Reihenfolge:
  1. Hartes Ausschlusskriterium (Negativliste, Verfahrensart)
  2. Deterministische Merkmale (CPV, Keywords, kVA-Band, Auftraggebertyp)
  3. Semantik (Embedding gegen das KSP-Profil) - fuer alles, was 1 und 2
     nicht erwischen

Die deterministische Schicht ist erklaerbar. Jeder Punkt hat eine Begruendung,
die im Dossier auftaucht - das ist der Unterschied zu einem Score, dem man
glauben muss.
"""
from __future__ import annotations

import re

from .config import (
    CPV_CORE, CPV_WIDE, KEYWORDS_EXCLUDE_HARD, KEYWORDS_NEGATIVE,
    KEYWORDS_STRONG, KEYWORDS_WEAK,
    KVA_HARD_LIMIT, KVA_SWEET_SPOT, PORTFOLIO, SCORE_GO, SCORE_WATCH,
)
from .models import Notice

KVA_RE = re.compile(r"(\d{1,4}(?:[.,]\d+)?)\s*(kva|kw)\b", re.I)

BUYER_SIGNALS = {
    "feuerwehr": 12, "freiwillige feuerwehr": 12, "werkfeuerwehr": 10,
    "thw": 12, "technisches hilfswerk": 12,
    "katastrophenschutz": 12, "bevoelkerungsschutz": 12, "bevölkerungsschutz": 12,
    "stadt": 6, "gemeinde": 6, "landkreis": 6, "amt ": 6, "kreis": 5,
    "stadtwerke": 7, "wasserversorgung": 7, "wasserverband": 7,
    "zweckverband": 6, "klaeranlage": 5, "kläranlage": 5,
    "polizei": 8, "bundeswehr": 7, "bundespolizei": 8,
    "klinik": 6, "krankenhaus": 6, "rechenzentrum": 6,
}

PROCEDURE_PENALTY = {
    "vob": -10,          # reine Bauleistung, wir sind Lieferant
    "planungsleistung": -25,
    "vergebener auftrag": -100,   # schon vergeben
    "ex post": -100,
    "beabsichtigte": -8,          # Vorinformation: interessant, aber nicht handelbar
}


def extract_kva(text: str) -> float | None:
    """Groesste plausible Leistungsangabe aus dem Text."""
    vals: list[float] = []
    for raw, unit in KVA_RE.findall(text or ""):
        try:
            v = float(raw.replace(",", "."))
        except ValueError:
            continue
        if unit.lower() == "kw":
            v = v / 0.8          # kW -> kVA bei cos phi 0,8
        if 1 <= v <= 5000:
            vals.append(v)
    return max(vals) if vals else None


def score(n: Notice) -> Notice:
    pts = 0
    why: list[str] = []
    text = n.fulltext

    # --- Schicht 1: harte Ausschluesse ---------------------------------
    hard_hit = [k for k in KEYWORDS_EXCLUDE_HARD if k in text]
    if hard_hit:
        n.score = 0
        n.score_reasons = [f"Ausschluss: {', '.join(hard_hit)} - liefern wir nicht"]
        return n

    strong_hit = [k for k in KEYWORDS_STRONG if k in text]
    neg_hit = [k for k in KEYWORDS_NEGATIVE if k in text]
    if neg_hit and not strong_hit:
        n.score = 0
        n.score_reasons = [f"Ausschluss: {', '.join(neg_hit)} ohne Kernbegriff"]
        return n

    for marker, penalty in PROCEDURE_PENALTY.items():
        if marker in (n.procedure or "").lower() or marker in (n.kind or "").lower():
            pts += penalty
            why.append(f"{marker}: {penalty:+d}")

    # --- Schicht 2: deterministische Merkmale --------------------------
    core = [c for c in n.cpv if c[:8] in CPV_CORE]
    wide = [c for c in n.cpv if c[:8] in CPV_WIDE]
    if core:
        pts += 35
        why.append(f"CPV Kerncode {core[0][:8]} ({CPV_CORE[core[0][:8]]}): +35")
    elif wide:
        pts += 12
        why.append(f"CPV Randcode {wide[0][:8]}: +12")

    if strong_hit:
        pts += 30
        why.append(f"Kernbegriff im Text ({', '.join(strong_hit[:3])}): +30")
    else:
        weak_hit = [k for k in KEYWORDS_WEAK if k in text]
        if weak_hit:
            pts += 12
            why.append(f"Randbegriff ({', '.join(weak_hit[:3])}): +12")

    # Leistungsklasse
    kva = extract_kva(f"{n.title} {n.description}")
    n.kva = kva
    if kva:
        lo, hi = KVA_SWEET_SPOT
        hlo, hhi = KVA_HARD_LIMIT
        if lo <= kva <= hi:
            pts += 20
            why.append(f"{kva:.0f} kVA liegt im Portfolio: +20")
            n.matched_product = _match_product(kva)
        elif hlo <= kva <= hhi:
            pts += 3
            why.append(f"{kva:.0f} kVA am Rand des Portfolios: +3")
        else:
            pts -= 20
            why.append(f"{kva:.0f} kVA ausserhalb des Portfolios: -20")

    # Auftraggebertyp
    for signal, bonus in BUYER_SIGNALS.items():
        if signal in (n.buyer or "").lower():
            pts += bonus
            why.append(f"Auftraggeber '{signal.strip()}': +{bonus}")
            break

    # Lieferung schlaegt Wartung
    if any(w in text for w in ("lieferung", "beschaffung", "anschaffung", "liefern")):
        pts += 8
        why.append("Lieferleistung: +8")
    if "wartung" in text and not any(
        w in text for w in ("lieferung", "beschaffung", "anschaffung")
    ):
        pts -= 25
        why.append("reiner Wartungsauftrag ohne Lieferanteil: -25")

    n.score = max(0, min(100, pts))

    # Deckel: Was ausserhalb der Leistungsklasse liegt, ist nie ein
    # automatisches Go - unabhaengig davon, wie gut der Rest passt.
    if kva and not (KVA_SWEET_SPOT[0] <= kva <= KVA_SWEET_SPOT[1]):
        if n.score >= SCORE_GO:
            n.score = SCORE_GO - 1
            why.append(f"Deckel: {kva:.0f} kVA ausserhalb 20-200 kVA, kein Auto-Go")

    n.score_reasons = why
    return n


def _match_product(kva: float) -> str:
    for p in PORTFOLIO:
        if p.kva_min <= kva <= p.kva_max:
            return p.name
    return ""


def bucket(n: Notice) -> str:
    if n.score >= SCORE_GO:
        return "go"
    if n.score >= SCORE_WATCH:
        return "pruefen"
    return "ablage"


def score_all(notices: list[Notice]) -> list[Notice]:
    return sorted((score(n) for n in notices), key=lambda x: -x.score)
