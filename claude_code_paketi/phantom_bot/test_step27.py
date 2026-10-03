"""Adım 27: seans/Pazar/Asya yalnız forex; seans puanı teyit anına, kısıt bayrağı tarama anına göre."""
from datetime import datetime, timezone

import phantom_scan
import scoring
import sessions
import signals
import utils
from test_step15 import candle


def test_scope_by_market():
    # Pazar 22:00 UTC = 18:00 NY (yaz saati): Pazar açılış kısıtı. 00:30 UTC Salı-NY Pazartesi 20:30 = ASIA.
    sunday = datetime(2026, 10, 4, 22, 0, tzinfo=timezone.utc)
    asia = datetime(2026, 10, 6, 0, 30, tzinfo=timezone.utc)
    tags, restrictions, _ = phantom_scan._session_context("forex", "EUR/USD", sunday)
    assert "SUNDAY" in restrictions, restrictions
    tags, restrictions, _ = phantom_scan._session_context("forex", "EUR/USD", asia)
    assert "ASIA" in tags and "ASIA" in restrictions
    for moment in (sunday, asia):
        tags, restrictions, spread = phantom_scan._session_context("crypto", "BTCUSDT", moment)
        assert tags == [] and restrictions == [] and spread is False, (tags, restrictions, spread)
    rollover = datetime(2026, 10, 6, 21, 0, tzinfo=timezone.utc)  # 17:00 NY
    assert phantom_scan._session_context("forex", "EUR/USD", rollover)[2] is True
    assert phantom_scan._session_context("crypto", "BTCUSDT", rollover)[2] is False
    print("Kriptoda seans/SUNDAY/ASIA/rollover yok, forex'te var: GEÇTİ")


def _score(session_tags):
    return scoring.score_setup({"direction": "BULLISH", "stack_count": 1, "session_tags": session_tags,
                                "asia": "ASIA" in session_tags})["score"]


def test_scoring_follows_confirmation():
    assert _score(["LNDN"]) - _score([]) == 5
    assert _score([]) - _score(["ASIA"]) == 5
    print("Seans +5 / Asya -5 yalnız teyit etiketi varsa: GEÇTİ")


def test_confirmation_time():
    poi = {"direction": "BULLISH", "low": 100.0, "high": 101.0, "distal": 100.0,
           "proximal": 101.0, "eq": 100.5}
    base = 1790000000
    candles = [candle(103, 104, 102, 103, base), candle(103, 103.5, 100.4, 101, base + 900),
               candle(101, 102, 100.8, 101.5, base + 1800), candle(101.5, 103, 101, 102.5, base + 2700),
               candle(102.5, 103.2, 101.8, 102.0, base + 3600), candle(102.0, 102.2, 100.6, 100.8, base + 4500),
               candle(100.8, 101.9, 100.7, 101.8, base + 5400), candle(101.8, 102.6, 101.5, 102.4, base + 6300),
               candle(102.4, 105.0, 102.3, 104.8, base + 7200), candle(104.8, 105.5, 104.2, 105.2, base + 8100),
               candle(105.2, 105.6, 104.9, 105.3, base + 9000)]
    status = signals.ltf_status(poi, candles, [], 3)
    assert status["status"] == "ENTRY1_READY" and status["confirmation_time"] == base + 7200, status
    assert signals.ltf_status(poi, candles[:3], [], 3)["confirmation_time"] is None
    # Teyit anının seansı, tarama anından bağımsız hesaplanır.
    assert sessions.session_tags(datetime(2026, 10, 6, 7, 30, tzinfo=timezone.utc)) == ["LNDN"]
    print("Teyit zamanı BOS mumundan alınıyor: GEÇTİ")


def test_scan_candidate_uses_confirmation_session():
    import synth
    synth.isolate_dirs()
    lndn = int(datetime(2026, 10, 6, 7, 30, tzinfo=timezone.utc).timestamp())  # 03:30 NY = LNDN
    original = signals.ltf_status

    def fake(poi, *args, **kwargs):
        result = original(poi, *args, **kwargs)
        result.update(status="ENTRY2_READY", ltf_tf="5m", confirmation_time=lndn,
                      ltf_ob={"tf": "5m", "high": poi["proximal"], "low": poi["proximal"] * 0.999,
                              "proximal": poi["proximal"], "distal": poi["proximal"] * 0.999,
                              "eq": poi["proximal"] * 0.9995})
        return result

    signals.ltf_status = fake
    try:
        forex, _ = synth.scan(75, symbol="TEST/USD", market="forex")
        crypto, _ = synth.scan(75)
    finally:
        signals.ltf_status = original
    assert forex and all(item["session_tag"] == "LNDN" for item in forex), forex
    assert crypto and all(item["session_tag"] == "" for item in crypto), crypto
    assert any(row["criterion"] == "preferred_session" for row in forex[0]["score_breakdown"])
    assert not any(row["criterion"] in ("preferred_session", "asia_confirmation_penalty")
                   for row in crypto[0]["score_breakdown"])
    print("Aday seans etiketi teyit anından (forex), kriptoda boş: GEÇTİ")


def main():
    test_scope_by_market()
    test_scoring_follows_confirmation()
    test_confirmation_time()
    test_scan_candidate_uses_confirmation_session()
    print("test_step27: OK")


if __name__ == "__main__":
    main()
