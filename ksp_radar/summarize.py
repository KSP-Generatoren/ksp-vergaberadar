"""Zusammenfassung und Assistent-Antworten ohne API-Zwang.

Zwei Stufen:
  1. Regelbasiert (immer verfuegbar): deutscher Fliesstext aus den
     Bekanntmachungsfeldern. Ehrlich, ohne Halluzination, weil nur
     vorhandene Felder verwendet werden.
  2. Claude API (wenn ANTHROPIC_API_KEY gesetzt): ersetzt die regelbasierte
     Fassung durch eine echte Zusammenfassung der Vergabeunterlagen.

Die Actions-Pipeline ruft erst Stufe 1 fuer alles, dann Stufe 2 fuer die
Top-Treffer, sofern das Secret vorhanden ist.
"""
from __future__ import annotations

from .models import Notice

PROC_LABEL = {
    "vgv": "ein oberschwelliges Verfahren nach VgV",
    "uvgo": "ein unterschwelliges Verfahren nach UVgO",
    "vob": "ein Bauvergabeverfahren nach VOB/A",
    "sektvo": "ein Sektorenverfahren nach SektVO",
}


def summary(n: Notice) -> str:
    parts: list[str] = []
    who = n.buyer or "Eine Vergabestelle"
    what = n.title or "eine Leistung"
    parts.append(f"{who} schreibt aus: {what}.")

    proc = (n.procedure or "").lower()
    label = next((v for k, v in PROC_LABEL.items() if k in proc), "")
    bits = []
    if label:
        bits.append(f"Es handelt sich um {label}")
    if "beschränkt" in proc or "beschraenkt" in proc:
        bits.append("als beschränkte Ausschreibung")
    if "rahmen" in (n.title or "").lower():
        bits.append("mit Rahmenvereinbarungscharakter")
    if bits:
        parts.append(", ".join(bits) + ".")

    if n.kva:
        band = "im Kernbereich des KSP-Portfolios (20–200 kVA)" \
            if 20 <= n.kva <= 200 else "außerhalb des KSP-Kernbereichs von 20–200 kVA"
        parts.append(f"Die geforderte Leistungsklasse liegt bei etwa {n.kva:.0f} kVA und damit {band}.")

    if n.deadline:
        parts.append(f"Angebotsfrist: {n.deadline.strftime('%d.%m.%Y um %H:%M')} Uhr.")
    elif n.kind == "award":
        parts.append("Das Verfahren ist bereits vergeben und dient nur noch der Marktbeobachtung.")

    if n.matched_product:
        parts.append(f"Passendes Produkt: {n.matched_product}.")

    if n.documents_url:
        parts.append("Die Vergabeunterlagen sind über die in der Bekanntmachung "
                     "angegebene Adresse direkt abrufbar (§ 41 VgV / § 29 UVgO).")
    return " ".join(parts)


def faq(n: Notice) -> list[dict]:
    """Vorberechnete Fragen an die Bekanntmachung. Antworten nur aus Feldern,
    die tatsaechlich vorliegen — was fehlt, wird als fehlend benannt."""
    out = []
    if n.deadline:
        out.append({
            "q": "Bis wann läuft die Frist?",
            "a": f"Angebotsfrist ist der {n.deadline.strftime('%d.%m.%Y um %H:%M')} Uhr.",
            "c": "Bekanntmachung, Feld Angebotsfrist",
        })
    out.append({
        "q": "Wer ist die Vergabestelle?",
        "a": f"{n.buyer or 'Nicht angegeben'}{', ' + n.buyer_city if n.buyer_city else ''}.",
        "c": "Bekanntmachung, Auftraggeber",
    })
    if n.cpv:
        out.append({
            "q": "Wie ist die Leistung klassifiziert?",
            "a": f"CPV {', '.join(n.cpv[:3])}. "
                 + (f"Erkannte Leistungsklasse etwa {n.kva:.0f} kVA." if n.kva else
                    "Eine Leistungsklasse ist aus dem Bekanntmachungstext nicht ablesbar."),
            "c": "Bekanntmachung, CPV-Klassifikation",
        })
    out.append({
        "q": "Wo sind die Vergabeunterlagen?",
        "a": (f"Direkt abrufbar unter der Dokumentenadresse der Bekanntmachung "
              f"(ohne Registrierung, § 41 VgV / § 29 UVgO)." if n.documents_url
              else "Die Bekanntmachung enthält keine Dokumenten-URL — hier ist ein "
                   "manueller Blick ins Portal nötig."),
        "c": "eForms BT-15 Documents URL",
    })
    if n.score_reasons:
        out.append({
            "q": "Warum wurde das Verfahren so bewertet?",
            "a": " · ".join(n.score_reasons[:5]) + f" — Summe {n.score} von 100.",
            "c": "Bewertungswerk score.py",
        })
    return out
