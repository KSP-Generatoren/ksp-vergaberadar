"""KI-Dossier.

Erzeugt aus den Vergabeunterlagen genau das Dokument, das heute von Hand
entsteht: Ausschlussrisiken, Wertungshebel, Widersprueche, Go/No-Go.

Das Format ist nicht generisch, sondern das, was bei KSP intern ohnehin
verwendet wird. Genau darin liegt der Vorsprung gegenueber einem Produkt
von der Stange: Der Prompt kennt das eigene Datenblatt.
"""
from __future__ import annotations

import json
import logging
import os

from .config import PORTFOLIO, PROFILE_TEXT
from .models import Notice

log = logging.getLogger(__name__)

MODEL = os.getenv("RADAR_MODEL", "claude-sonnet-4-5")
MAX_DOC_CHARS = 400_000

SYSTEM = """Du bist Vergabereferent bei KSP Generatoren (QP International GmbH).
Du pruefst Vergabeunterlagen aus Bietersicht.

Arbeitsweise:
- Antworte ausschliesslich auf Basis der uebergebenen Unterlagen.
- Belege jede Aussage mit Dokumentname und Abschnitt oder Nummer.
- Wenn etwas nicht in den Unterlagen steht, schreibe das hin. Rate nicht.
- Achte besonders auf Formfehler, die zum Ausschluss fuehren: Aenderungen an
  den Vergabeunterlagen, eigene AGB, fehlende Erklaerungen, Fristen,
  Mindestanforderungen, Nachweise.
- Unterscheide zwischen "steht so in den Unterlagen" und "waere zu klaeren".

Produktprofil des Bieters:
{profile}

Portfolio:
{portfolio}
"""

TEMPLATE = """Analysiere die folgende Ausschreibung und liefere ein Dossier.

Bekanntmachung:
  Titel:        {title}
  Auftraggeber: {buyer}, {city}
  Verfahren:    {procedure}
  Frist:        {deadline}
  CPV:          {cpv}
  Vergabenummer: {source_id}

Vergabeunterlagen:
---
{documents}
---

Gib das Dossier als JSON in genau dieser Struktur zurueck:

{{
  "kurzfassung": "3-5 Saetze: worum geht es, passt es zu uns",
  "passung": {{
    "produkt": "welches KSP-Produkt passt, oder 'keines'",
    "technisch_erfuellt": ["Anforderung -> unser Wert"],
    "technisch_kritisch": ["Anforderung -> warum knapp oder offen"],
    "technisch_nicht_erfuellt": ["Anforderung -> warum nicht"]
  }},
  "ausschlussrisiken": [
    {{"risiko": "...", "fundstelle": "Dokument, Abschnitt", "gegenmassnahme": "..."}}
  ],
  "wertung": {{
    "kriterien": [{{"kriterium": "...", "gewicht": "...", "hebel": "..."}}],
    "hinweis": "wo Uebererfuellung wirklich Punkte bringt"
  }},
  "widersprueche": [
    {{"beobachtung": "...", "fundstellen": ["...", "..."], "empfehlung": "..."}}
  ],
  "einzureichen": ["Formblatt/Nachweis 1", "..."],
  "offene_punkte": ["was intern geklaert werden muss"],
  "empfehlung": {{"entscheidung": "go|pruefen|no-go", "begruendung": "...", "vertrauen": "hoch|mittel|niedrig"}}
}}

Nur das JSON, kein weiterer Text."""


def build(notice: Notice, documents_text: str, api_key: str | None = None) -> dict:
    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError("pip install anthropic")

    client = Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
    portfolio = "\n".join(
        f"- {p.name}: {p.kva_min:.0f}-{p.kva_max:.0f} kVA, {p.bauform}\n"
        + "\n".join(f"    * {m}" for m in p.merkmale)
        for p in PORTFOLIO
    )

    prompt = TEMPLATE.format(
        title=notice.title,
        buyer=notice.buyer,
        city=notice.buyer_city,
        procedure=notice.procedure,
        deadline=notice.deadline.isoformat() if notice.deadline else "keine angegeben",
        cpv=", ".join(notice.cpv),
        source_id=notice.source_id,
        documents=documents_text[:MAX_DOC_CHARS] or "(keine Unterlagen abrufbar)",
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM.format(profile=PROFILE_TEXT, portfolio=portfolio),
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.error("Dossier nicht als JSON lesbar")
        return {"fehler": "Antwort nicht als JSON lesbar", "rohtext": text}


def ask(notice: Notice, documents_text: str, question: str,
        api_key: str | None = None) -> str:
    """Freie Frage an die Unterlagen. Antwort ausschliesslich aus den Dokumenten."""
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=(
            "Beantworte die Frage ausschliesslich aus den uebergebenen "
            "Vergabeunterlagen. Nenne zu jeder Aussage Dokument und Abschnitt. "
            "Steht die Antwort nicht in den Unterlagen, sage das."
        ),
        messages=[{"role": "user", "content":
                   f"Unterlagen zu '{notice.title}':\n---\n"
                   f"{documents_text[:MAX_DOC_CHARS]}\n---\n\nFrage: {question}"}],
    )
    return resp.content[0].text
