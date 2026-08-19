"""Aenderungsmonitor am realen Fall Bad Oldesloe."""
import sys, pathlib
from datetime import datetime, timezone
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ksp_radar.models import DocumentSnapshot
from ksp_radar.monitor import compare, summarize

T0 = """LV Nr. 1.6 Schallleistungspegel LWA maximal 90 dB(A).
LV Nr. 3.2 Zulassung wird vom Auftragnehmer beantragt."""
T1 = """LV Nr. 1.6 Schalldruckpegel in 7 m maximal 65 dB(A). Angabe als LWA wird nicht akzeptiert.
LV Nr. 3.2 Zulassung wird vom Auftraggeber in Stormarn beantragt."""


def snap(files, text, day):
    return DocumentSnapshot("uid1", datetime(2026, 8, day, tzinfo=timezone.utc), files, text)


def test_erstabzug():
    ch = compare(None, snap({"LV.pdf": "aa"}, T0, 1))
    assert len(ch) == 1 and ch[0].kind == "neu"


def test_bieterinfo_ist_kritisch():
    ch = compare(snap({"LV.pdf": "aa"}, T0, 1),
                 snap({"LV.pdf": "aa", "Bieterinformation_3.pdf": "bb"}, T0, 5))
    assert any(c.severity == "kritisch" and c.filename == "Bieterinformation_3.pdf" for c in ch)


def test_frist_relevante_textaenderung_ist_kritisch():
    ch = compare(snap({"LV.pdf": "aa"}, T0, 1), snap({"LV.pdf": "cc"}, T1, 5))
    vol = [c for c in ch if c.filename == "(Volltext)"]
    assert vol and vol[0].severity == "kritisch"
    assert "Schalldruckpegel" in vol[0].diff


def test_identischer_stand_meldet_nichts():
    a, b = snap({"LV.pdf": "aa"}, T0, 1), snap({"LV.pdf": "aa"}, T0, 2)
    assert compare(a, b) == [] and a.digest == b.digest


def test_zusammenfassung():
    ch = compare(snap({"LV.pdf": "aa"}, T0, 1), snap({"LV.pdf": "cc"}, T1, 5))
    assert "Auswirkung auf das Angebot" in summarize(ch)
