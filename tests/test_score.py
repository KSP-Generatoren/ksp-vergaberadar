"""Bewertungswerk gegen die realen Faelle."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ksp_radar.export import load_seed
from ksp_radar.score import score_all, bucket, extract_kva


def scored():
    notices, _ = load_seed()
    return {n.source_id: n for n in score_all(notices)}


def test_kernfall_moenchengladbach_ist_go():
    s = scored()["MG-FWA-NEA-2026"]
    assert bucket(s) == "go" and s.score >= 90
    assert s.matched_product.startswith("KSP-50Y")


def test_bad_oldesloe_ist_go():
    assert bucket(scored()["11.81.01.0020"]) == "go"


def test_lastbank_wird_ausgeschlossen():
    s = scored()["MARARS-LASTBANK"]
    assert s.score == 0
    assert "liefern wir nicht" in s.score_reasons[0]


def test_bhkw_wird_ausgeschlossen():
    assert scored()["MVA-WEISWEILER-KWK"].score == 0


def test_vergebene_auftraege_fallen_raus():
    assert scored()["LZPD-RV-NEA"].score == 0


def test_reiner_wartungsauftrag_faellt_raus():
    assert bucket(scored()["UKA-WARTUNG-10KV"]) == "ablage"


def test_kva_ausserhalb_portfolio_nie_auto_go():
    for sid in ("SWA-MOBIL-250-330", "CLP-NEA-630", "DLR-BS-1000"):
        s = scored()[sid]
        assert s.score < 70, f"{sid} haette gedeckelt werden muessen ({s.score})"


def test_jeder_score_hat_begruendung():
    for s in scored().values():
        if s.score > 0:
            assert s.score_reasons, f"{s.source_id} ohne Begruendung"


def test_kva_extraktion():
    assert extract_kva("Netzersatzanlage 630 kVA") == 630
    assert extract_kva("zwei 400V/1000 kVA Aggregate") == 1000
    assert abs(extract_kva("Aggregat 40 kW") - 50) < 0.1   # cos phi 0,8
    assert extract_kva("ohne Angabe") is None
