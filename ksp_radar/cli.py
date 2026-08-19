"""Kommandozeile.

  python -m ksp_radar.cli sync            alle Quellen abrufen, bewerten, speichern
  python -m ksp_radar.cli list            aktuelle Treffer anzeigen
  python -m ksp_radar.cli docs <uid>      Vergabeunterlagen holen
  python -m ksp_radar.cli watch           Aenderungsmonitor ueber alle aktiven Verfahren
  python -m ksp_radar.cli dossier <uid>   KI-Dossier erzeugen
  python -m ksp_radar.cli export          data/notices.json fuer die Weboberflaeche
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from . import db, documents, monitor, score
from .config import SCORE_GO, SCORE_WATCH
from .models import Notice
from .sources import cosinex, doe, nrw, ted

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ksp_radar")


def cmd_sync(args) -> None:
    conn = db.connect()
    collected: list[Notice] = []
    status: list[dict] = []

    for name, fn in [
        ("TED", lambda: ted.fetch(days=args.days)),
        ("Datenservice Bund", lambda: doe.fetch(days=args.days)),
        ("Vergabe.NRW", lambda: nrw.fetch(days=args.days)),
        ("cosinex", lambda: cosinex.fetch_all()),
    ]:
        try:
            batch = fn()
            log.info("%-24s %4d Datensaetze", name, len(batch))
            collected.extend(batch)
            status.append({"name": name, "ok": True, "count": len(batch), "error": ""})
        except Exception as exc:                      # noqa: BLE001
            log.warning("%-24s FEHLER: %s", name, exc)
            status.append({"name": name, "ok": False, "count": 0, "error": str(exc)[:200]})

    scored = score.score_all(collected)
    new = sum(db.upsert_notice(conn, n) for n in scored)
    go = sum(1 for n in scored if n.score >= SCORE_GO)

    from pathlib import Path
    Path("data").mkdir(exist_ok=True)
    Path("data/status.json").write_text(json.dumps({
        "last_sync": datetime.now().isoformat(timespec="seconds"),
        "sources": status,
        "total": len(scored), "new": new, "go": go,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{len(scored)} Datensaetze, {new} neu, {go} mit Score >= {SCORE_GO}")
    ok_sources = sum(1 for st in status if st["ok"])
    print(f"Quellen erreichbar: {ok_sources}/{len(status)}")
    if args.strict and ok_sources == 0:
        sys.exit("Keine Quelle erreichbar - Abbruch (--strict)")


def cmd_list(args) -> None:
    conn = db.connect()
    rows = conn.execute(
        "SELECT * FROM notice WHERE score >= ? ORDER BY score DESC, deadline ASC LIMIT ?",
        (args.min_score, args.limit),
    ).fetchall()
    for r in rows:
        dl = (r["deadline"] or "")[:16].replace("T", " ")
        print(f"{r['score']:>3}  {dl:<16}  {r['buyer'][:28]:<28}  {r['title'][:60]}")
    print(f"\n{len(rows)} Treffer")


def cmd_docs(args) -> None:
    conn = db.connect()
    row = conn.execute("SELECT * FROM notice WHERE uid = ?", (args.uid,)).fetchone()
    if not row:
        sys.exit(f"Unbekannte uid {args.uid}")
    snap = documents.fetch_documents(row["uid"], row["documents_url"])
    if not snap:
        sys.exit("Keine Unterlagen abrufbar")
    db.save_snapshot(conn, snap)
    print(f"{len(snap.files)} Dateien, {len(snap.text):,} Zeichen Text")


def cmd_watch(args) -> None:
    conn = db.connect()
    rows = conn.execute(
        "SELECT * FROM notice WHERE documents_url != '' AND score >= ? "
        "AND (deadline IS NULL OR deadline >= ?)",
        (SCORE_WATCH, datetime.now().isoformat()),
    ).fetchall()

    total = 0
    for r in rows:
        old = db.latest_snapshot(conn, r["uid"])
        new = documents.fetch_documents(r["uid"], r["documents_url"])
        if not new:
            continue
        if old and old.digest == new.digest:
            continue
        db.save_snapshot(conn, new)
        for c in monitor.compare(old, new):
            conn.execute(
                "INSERT INTO change (notice_uid, kind, filename, severity, diff) "
                "VALUES (?,?,?,?,?)",
                (c.notice_uid, c.kind, c.filename, c.severity, c.diff[:20000]),
            )
            total += 1
            marker = {"kritisch": "!!", "wichtig": " !", "info": "  "}[c.severity]
            print(f"{marker} {r['title'][:55]:<55} {c.kind:<10} {c.filename}")
    conn.commit()
    print(f"\n{len(rows)} Verfahren geprueft, {total} Aenderung(en)")


def cmd_dossier(args) -> None:
    from . import dossier as dossier_mod
    conn = db.connect()
    row = conn.execute("SELECT * FROM notice WHERE uid = ?", (args.uid,)).fetchone()
    if not row:
        sys.exit(f"Unbekannte uid {args.uid}")
    snap = db.latest_snapshot(conn, args.uid)
    n = Notice(source=row["source"], source_id=row["source_id"], title=row["title"],
               description=row["description"] or "", buyer=row["buyer"] or "",
               buyer_city=row["buyer_city"] or "", procedure=row["procedure"] or "",
               cpv=json.loads(row["cpv"] or "[]"),
               deadline=datetime.fromisoformat(row["deadline"]) if row["deadline"] else None)
    payload = dossier_mod.build(n, snap.text if snap else "")
    conn.execute("INSERT OR REPLACE INTO dossier (notice_uid, payload) VALUES (?,?)",
                 (args.uid, json.dumps(payload, ensure_ascii=False)))
    conn.commit()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_build(args) -> None:
    """Site bauen: DB-Bestand, sonst Seed. Ergebnis in docs/."""
    from . import export as ex
    from . import summarize
    from .models import Notice as N

    conn = db.connect()
    rows = conn.execute("SELECT * FROM notice ORDER BY score DESC").fetchall()

    notices: list[Notice] = []
    if rows:
        for r in rows:
            notices.append(N(
                source=r["source"], source_id=r["source_id"], title=r["title"] or "",
                description=r["description"] or "", buyer=r["buyer"] or "",
                buyer_city=r["buyer_city"] or "", nuts=r["nuts"] or "",
                cpv=json.loads(r["cpv"] or "[]"), procedure=r["procedure"] or "",
                kind=r["kind"] or "notice", value_eur=r["value_eur"],
                published=date.fromisoformat(r["published"]) if r["published"] else None,
                deadline=datetime.fromisoformat(r["deadline"]) if r["deadline"] else None,
                notice_url=r["notice_url"] or "", documents_url=r["documents_url"] or "",
            ))
        notices = score.score_all(notices)
        ch_rows = conn.execute(
            "SELECT c.*, n.title FROM change c JOIN notice n ON n.uid=c.notice_uid "
            "ORDER BY detected_at DESC LIMIT 40").fetchall()
        changes = [{
            "id": r["notice_uid"], "sev": r["severity"], "when": r["detected_at"],
            "file": r["filename"], "what": r["kind"],
            "diff": [["ctx", line] for line in (r["diff"] or "").splitlines()[:12]],
            "impact": "",
        } for r in ch_rows]
        origin = f"{len(rows)} Datensaetze aus der Datenbank"
    else:
        notices, changes = ex.load_seed()
        notices = score.score_all(notices)
        origin = "Seed-Datensatz (22 recherchierte Bekanntmachungen) - noch kein Live-Sync"

    payload = []
    for n in notices:
        payload.append(ex.notice_payload(n, {
            "summary": summarize.summary(n),
            "faq": summarize.faq(n),
            "vergabenummer": getattr(n, "_vergabenummer", ""),
        }))

    try:
        st = json.loads(Path("data/status.json").read_text(encoding="utf-8"))
        sources = st.get("sources", [])
        last = st.get("last_sync", "")
    except (OSError, json.JSONDecodeError):
        sources, last = [], ""
    if not sources:
        sources = [{"name": nm, "ok": None, "count": 0, "error": "noch kein Sync"}
                   for nm in ("TED", "Datenservice Bund", "Vergabe.NRW", "cosinex")]
    for s_ in sources:
        s_["last"] = last

    out = ex.build_site(payload, changes, sources)
    print(f"Site gebaut: {out}  ({origin})")


def cmd_export(args) -> None:
    conn = db.connect()
    rows = conn.execute("SELECT * FROM notice ORDER BY score DESC").fetchall()
    out = [dict(r) for r in rows]
    for r in out:
        r["cpv"] = json.loads(r["cpv"] or "[]")
        r["score_reasons"] = json.loads(r["score_reasons"] or "[]")
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"{len(out)} Datensaetze -> {args.out}")


def main() -> None:
    p = argparse.ArgumentParser(prog="ksp_radar")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sync");    s.add_argument("--days", type=int, default=7)
    s.add_argument("--strict", action="store_true"); s.set_defaults(fn=cmd_sync)
    s = sub.add_parser("list");    s.add_argument("--min-score", type=int, default=SCORE_WATCH)
    s.add_argument("--limit", type=int, default=50); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("docs");    s.add_argument("uid"); s.set_defaults(fn=cmd_docs)
    s = sub.add_parser("watch");   s.set_defaults(fn=cmd_watch)
    s = sub.add_parser("dossier"); s.add_argument("uid"); s.set_defaults(fn=cmd_dossier)
    s = sub.add_parser("export");  s.add_argument("--out", default="data/notices.json"); s.set_defaults(fn=cmd_export)
    s = sub.add_parser("build");   s.set_defaults(fn=cmd_build)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
