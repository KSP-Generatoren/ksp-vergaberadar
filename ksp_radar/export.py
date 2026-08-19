"""Baut die auslieferbare Site: docs/index.html, RSS-Feed, Kalender, Rohdaten.

Die Daten werden INLINE in die HTML geschrieben. Kein fetch(), kein CORS,
kein Server: dieselbe Datei laeuft auf GitHub Pages, per Doppelklick vom
Desktop und als Anhang im Chat.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from .models import Notice
from .score import bucket

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "web" / "template.html"
DOCS = ROOT / "docs"


def notice_payload(n: Notice, extra: dict | None = None) -> dict:
    d = n.to_dict()
    d["bucket"] = bucket(n)
    if extra:
        d.update(extra)
    return d


def build_site(notices: list[dict], changes: list[dict], sources: list[dict],
               analyses: dict | None = None, out_dir: Path = DOCS) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(exist_ok=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": sources,
        "notices": notices,
        "changes": changes,
        "analyses": analyses or {},
    }

    raw = json.dumps(payload, ensure_ascii=False)
    # </script> im Datenstrom darf das HTML nicht beenden
    raw = raw.replace("</", "<\\/")

    html = TEMPLATE.read_text(encoding="utf-8")
    if "__DATA__" not in html:
        raise RuntimeError("Template ohne __DATA__-Platzhalter")
    html = html.replace("__DATA__", raw)

    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / "data" / "ui-data.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "feed.xml").write_text(rss(notices), encoding="utf-8")
    (out_dir / "fristen.ics").write_text(ics(notices), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return out_dir / "index.html"


# ---------------------------------------------------------------- RSS
def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def rss(notices: list[dict], limit: int = 50) -> str:
    rows = [n for n in notices if n.get("bucket") != "ablage"][:limit]
    items = []
    for n in rows:
        dl = n.get("deadline")
        desc = f"Passung {n.get('score', 0)}/100"
        if dl:
            desc += f" · Frist {dl[:10]}"
        if n.get("buyer"):
            desc += f" · {n['buyer']}"
        items.append(
            "<item>"
            f"<title>{_esc(n.get('title', ''))}</title>"
            f"<link>{_esc(n.get('notice_url') or 'https://oeffentlichevergabe.de')}</link>"
            f"<guid isPermaLink=\"false\">{n.get('uid', '')}</guid>"
            f"<description>{_esc(desc)}</description>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        "<title>KSP Vergaberadar</title>"
        "<link>https://oeffentlichevergabe.de</link>"
        "<description>Relevante Ausschreibungen für Netzersatzanlagen, "
        "bewertet gegen das KSP-Portfolio</description>"
        + "".join(items) + "</channel></rss>\n"
    )


# ---------------------------------------------------------------- ICS
def _ics_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\n", "\\n")


def ics(notices: list[dict]) -> str:
    ev = []
    for n in notices:
        dl = n.get("deadline")
        if not dl or n.get("bucket") == "ablage":
            continue
        try:
            dt = datetime.fromisoformat(dl)
        except ValueError:
            continue
        stamp = dt.strftime("%Y%m%dT%H%M%S")
        ev.append(
            "BEGIN:VEVENT\r\n"
            f"UID:{n.get('uid', '')}@ksp-vergaberadar\r\n"
            f"DTSTART:{stamp}\r\n"
            f"DTEND:{stamp}\r\n"
            f"SUMMARY:{_ics_escape('Angebotsfrist: ' + n.get('title', '')[:80])}\r\n"
            f"DESCRIPTION:{_ics_escape((n.get('buyer') or '') + ' · Passung ' + str(n.get('score', 0)) + '/100')}\r\n"
            "BEGIN:VALARM\r\nTRIGGER:-P3D\r\nACTION:DISPLAY\r\n"
            f"DESCRIPTION:{_ics_escape('Frist in 3 Tagen: ' + n.get('title', '')[:60])}\r\nEND:VALARM\r\n"
            "END:VEVENT\r\n"
        )
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        "PRODID:-//KSP Vergaberadar//DE\r\n"
        "X-WR-CALNAME:KSP Angebotsfristen\r\n"
        + "".join(ev) + "END:VCALENDAR\r\n"
    )


# ---------------------------------------------------------------- Seed-Loader
def load_seed() -> tuple[list[Notice], list[dict]]:
    """Die 22 recherchierten Bekanntmachungen + Aenderungs-Seed.

    Wird verwendet, solange noch kein Live-Sync gelaufen ist, damit die Site
    nie leer baut. Nach dem ersten erfolgreichen Sync ersetzt der DB-Bestand
    den Seed automatisch.
    """
    raw = json.loads((ROOT / "data" / "real_notices.json").read_text(encoding="utf-8"))
    notices = []
    for r in raw:
        r = dict(r)
        vn = r.pop("vergabenummer", None)
        if r.get("published"):
            r["published"] = date.fromisoformat(r["published"])
        if r.get("deadline"):
            r["deadline"] = datetime.fromisoformat(r["deadline"])
        n = Notice(**r)
        if vn:
            n.source_id = n.source_id  # uid bleibt stabil
            setattr(n, "_vergabenummer", vn)
        notices.append(n)
    changes = json.loads((ROOT / "data" / "changes_seed.json").read_text(encoding="utf-8"))
    return notices, changes
