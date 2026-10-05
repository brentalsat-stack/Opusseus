"""Adım 37: aktif aralık/protected/targeted tutarlılığı (CHoCH aralığı bozmaz, aralık son swing uç noktasına uzar);
UNDEFINED 4h bias'ta özet tablosu protected/targeted yerine '—' gösterir."""
import indicators
import report
import structure
import synth
import phantom_scan
from datetime import datetime, timezone
from test_step33 import section


def candle(o, h, l, c, t):
    return {"t": t, "o": float(o), "h": float(h), "l": float(l), "c": float(c), "v": 1.0}


def test_range_extends_to_latest_swing():
    # Yükseliş: swing low 5 (idx 2), swing high 10 (idx 5); idx 8 kapanışla 10'u kırar (BOS, protected low 5).
    # BOS'tan sonra 14 (idx 10) swing high oluşur: aralık tepesi ve targeted 14 olmalı (10 değil).
    rows = [(8, 9, 7, 8), (7, 8, 6, 7), (6, 7, 5, 6), (7, 8, 6, 7.5), (8, 9, 7, 8.5), (9, 10, 8, 9.5),
            (9, 9.5, 7.5, 8), (8, 9, 7.5, 8.5), (9, 12, 8.5, 11.5), (11.5, 13, 11, 12.5),
            (12.5, 14, 12, 13), (12.5, 13, 11.5, 12), (12, 12.5, 11, 11.5), (11.5, 12, 11, 11.8)]
    candles = [candle(*row, t=i) for i, row in enumerate(rows)]
    result = structure.analyze_structure(candles)
    assert result["trend"] == "BULLISH", result["trend"]
    assert result["protected"]["price"] == 5 and result["range_low"] == 5
    assert result["targeted"]["price"] == 14 and result["range_high"] == 14, result
    assert result["protected"]["price"] != result["targeted"]["price"]
    print("Aralık, BOS sonrası son swing tepesine uzuyor; targeted = aralık tepesi: GEÇTİ")


def test_choch_keeps_old_range():
    # Önceki testin devamı: protected low 5 altında kapanış (CHoCH) — eski aralık ve seviyeler korunur.
    rows = [(8, 9, 7, 8), (7, 8, 6, 7), (6, 7, 5, 6), (7, 8, 6, 7.5), (8, 9, 7, 8.5), (9, 10, 8, 9.5),
            (9, 9.5, 7.5, 8), (8, 9, 7.5, 8.5), (9, 12, 8.5, 11.5), (11.5, 13, 11, 12.5),
            (12.5, 14, 12, 13), (12.5, 13, 11.5, 12), (12, 12.5, 11, 11.5), (11.5, 12, 11, 11.8),
            (11.8, 12, 4, 4.5)]
    candles = [candle(*row, t=i) for i, row in enumerate(rows)]
    result = structure.analyze_structure(candles)
    assert result["trend"] == "CHOCH_BEARISH", result["trend"]
    assert result["protected"] == {"type": "low", "price": 5, "index": 2}, result["protected"]
    assert result["targeted"]["type"] == "high" and result["targeted"]["price"] == 14
    assert (result["range_low"], result["range_high"]) == (5, 14)
    print("CHoCH eski trendin protected/targeted/aralığını bozmuyor: GEÇTİ")


def test_invariants_on_random_series():
    extended = 0
    for seed in range(60):
        candles = synth.make_series(seed, "4h", 160)
        result = structure.analyze_structure(candles)
        protected, targeted = result["protected"], result["targeted"]
        if result["range_low"] is None:
            continue
        assert result["range_low"] <= result["range_high"], (seed, result)
        assert protected is not None and targeted is not None
        assert protected["price"] != targeted["price"], (seed, protected, targeted)
        assert {protected["type"], targeted["type"]} == {"low", "high"}, (seed, protected, targeted)
        assert {protected["price"], targeted["price"]} == {result["range_low"], result["range_high"]}, (seed, result)
        bullish = protected["type"] == "low"
        assert (protected["price"] < targeted["price"]) == bullish, (seed, protected, targeted)
        extended += 1
    assert extended >= 20, extended
    print("60 sentetik seride protected/targeted/aralık tutarlı ({} seri aralıklı): GEÇTİ".format(extended))


def test_summary_blanks_undefined():
    synth.isolate_dirs()
    for seed in range(40):
        _, summary = synth.scan(seed)
        if summary["htf_bias_h4"] == "UNDEFINED":
            assert summary["protected"] is None and summary["targeted"] is None, summary
            break
    else:
        raise AssertionError("UNDEFINED 4h bias'lı sentetik seri bulunamadı")
    meta = {"scan_time_utc": datetime(2026, 10, 3, tzinfo=timezone.utc), "market": "crypto",
            "symbols_scanned": 1, "duration_seconds": 1, "error_count": 0, "errors": [],
            "symbols": [dict(summary, symbol="UNDEFUSDT", market="crypto")]}
    markdown = open(report.write_reports([], meta)["md"], encoding="utf-8").read()
    row = next(line for line in section(markdown, "Sembol başına HTF").splitlines() if "UNDEFUSDT" in line)
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert cells[3] == "—" and cells[4] == "—", row
    print("4H UNDEFINED iken özet tablosunda protected/targeted '—': GEÇTİ")


def main():
    test_range_extends_to_latest_swing()
    test_choch_keeps_old_range()
    test_invariants_on_random_series()
    test_summary_blanks_undefined()
    print("test_step37: OK")


if __name__ == "__main__":
    main()
