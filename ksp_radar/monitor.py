"""Aenderungsmonitor.

Der Baustein mit dem besten Verhaeltnis von Aufwand zu Nutzen - und der,
den kein kommerzielles Portal anbietet.

Hintergrund: Wer die Vergabeunterlagen registrierungsfrei zieht, ist der
Vergabestelle unbekannt und bekommt keine Benachrichtigung ueber Aenderungen.
Das ist das bekannte Praxisproblem der direkten Bereitstellung - Bieter
reichen auf Basis veralteter Unterlagen ein und werden formal ausgeschlossen.

Beispiel Bad Oldesloe (11.81.01.0020): drei Bieterinformationen innerhalb von
sieben Tagen, jede mit materieller Auswirkung auf das Angebot.
"""
from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass

from .models import DocumentSnapshot

log = logging.getLogger(__name__)


@dataclass
class Change:
    notice_uid: str
    kind: str                 # "neu" | "geaendert" | "entfernt"
    filename: str
    diff: str = ""
    severity: str = "info"    # info | wichtig | kritisch


# Begriffe, deren Aenderung ein Angebot kippen kann.
CRITICAL_TERMS = [
    "frist", "angebotsfrist", "bindefrist", "termin",
    "schalldruck", "schallleistung", "db(a)",
    "eignung", "nachweis", "eigenerklaerung", "eigenerklärung",
    "mindestanforderung", "ausschluss", "zwingend",
    "lieferzeit", "gewaehrleistung", "gewährleistung",
    "vertragsstrafe", "sicherheitsleistung", "wertung", "zuschlagskriterien",
    "herstellung in der europaeischen", "herstellung in der europäischen",
]


def compare(old: DocumentSnapshot | None, new: DocumentSnapshot) -> list[Change]:
    if old is None:
        return [Change(new.notice_uid, "neu", "(Erstabzug)",
                       f"{len(new.files)} Dateien erfasst", "info")]

    changes: list[Change] = []
    old_files, new_files = set(old.files), set(new.files)

    for name in sorted(new_files - old_files):
        changes.append(Change(new.notice_uid, "neu", name,
                              "Datei neu hinzugekommen", _severity(name)))
    for name in sorted(old_files - new_files):
        changes.append(Change(new.notice_uid, "entfernt", name,
                              "Datei nicht mehr vorhanden", "wichtig"))
    for name in sorted(old_files & new_files):
        if old.files[name] != new.files[name]:
            changes.append(Change(new.notice_uid, "geaendert", name,
                                  "Inhalt geaendert", _severity(name)))

    if old.text and new.text and old.text != new.text:
        diff = "\n".join(list(difflib.unified_diff(
            old.text.splitlines(), new.text.splitlines(),
            fromfile="vorher", tofile="jetzt", n=1, lineterm="",
        ))[:400])
        sev = "kritisch" if any(t in diff.lower() for t in CRITICAL_TERMS) else "wichtig"
        changes.append(Change(new.notice_uid, "geaendert", "(Volltext)", diff, sev))

    return changes


def _severity(filename: str) -> str:
    low = filename.lower()
    if any(t in low for t in ("bieterinfo", "bieterinformation", "aenderung",
                              "änderung", "korrektur", "nachtrag", "berichtigung")):
        return "kritisch"
    return "info"


def summarize(changes: list[Change]) -> str:
    if not changes:
        return "Keine Aenderungen."
    crit = [c for c in changes if c.severity == "kritisch"]
    head = f"{len(changes)} Aenderung(en)"
    if crit:
        head += f", davon {len(crit)} mit moeglicher Auswirkung auf das Angebot"
    return head
