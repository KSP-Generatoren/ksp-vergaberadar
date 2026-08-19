"""Site-Build: HTML, RSS, ICS, Datenvertrag."""
import json, sys, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from lxml import etree
from ksp_radar import export as ex
from ksp_radar import summarize
from ksp_radar.score import score_all


def build(tmp):
    notices, changes = ex.load_seed()
    notices = score_all(notices)
    payload = [ex.notice_payload(n, {"summary": summarize.summary(n),
                                     "faq": summarize.faq(n)}) for n in notices]
    out = ex.build_site(payload, changes,
                        [{"name": "TED", "ok": True, "count": 5, "error": "", "last": ""}],
                        out_dir=pathlib.Path(tmp))
    return pathlib.Path(tmp), payload


def test_html_baut_und_enthaelt_daten():
    with tempfile.TemporaryDirectory() as tmp:
        d, payload = build(tmp)
        html = (d / "index.html").read_text(encoding="utf-8")
        assert "__DATA__" not in html
        assert "Notfallinformationspunkte Steinburg" in html
        assert "<\\/" in html or "</script>" not in json.dumps(payload)


def test_rss_ist_valides_xml_mit_items():
    with tempfile.TemporaryDirectory() as tmp:
        d, _ = build(tmp)
        root = etree.fromstring((d / "feed.xml").read_bytes())
        items = root.findall(".//item")
        assert len(items) >= 10
        assert root.findtext(".//title") == "KSP Vergaberadar"


def test_ics_enthaelt_offene_fristen():
    with tempfile.TemporaryDirectory() as tmp:
        d, payload = build(tmp)
        ics = (d / "fristen.ics").read_text(encoding="utf-8")
        expected = sum(1 for n in payload if n.get("deadline") and n["bucket"] != "ablage")
        assert ics.count("BEGIN:VEVENT") == expected >= 8
        assert "VALARM" in ics


def test_summary_ohne_api_ist_deutsch_und_faktentreu():
    notices, _ = ex.load_seed()
    n = next(x for x in score_all(notices) if x.source_id == "MG-FWA-NEA-2026")
    s = summarize.summary(n)
    assert "Mönchengladbach" in s and "50 kVA" in s and "11.09.2026" in s


def test_faq_meldet_fehlende_dokumenturl():
    notices, _ = ex.load_seed()
    n = next(x for x in score_all(notices) if x.source_id == "11.81.01.0020")
    faq = summarize.faq(n)
    doc_q = next(f for f in faq if "Vergabeunterlagen" in f["q"])
    assert "manueller Blick" in doc_q["a"]
