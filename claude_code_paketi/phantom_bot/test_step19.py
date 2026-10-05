"""Adım 19: mitigated/invalid OB'ler stacking'e katılmaz."""
import orderblocks
import phantom_scan
import synth
from test_step15 import candle


def _ob(tf):
    return {"direction": "BULLISH", "timeframe": tf, "low": 100.0, "high": 102.0,
            "distal": 100.0, "proximal": 102.0, "eq": 101.0, "bos_index": 0, "state": "FRESH"}


def main():
    synth.isolate_dirs()
    healthy = [candle(110, 111, 108, 110, i) for i in range(6)]            # bölgeye hiç inmez
    broken = [candle(110, 111, 108, 110, 0), candle(110, 111, 98, 99, 1),  # distal altı gövde kapanışı
              candle(99, 100, 97, 98, 2)]
    mitigated = [candle(110, 111, 108, 110, 0), candle(110, 111, 100.5, 105, 1),  # EQ'ya ulaşır
                 candle(105, 108, 104, 107, 2)]

    d1_invalid = phantom_scan._active_obs("T", [_ob("1day")], broken)
    d1_mitigated = phantom_scan._active_obs("T", [_ob("1day")], mitigated)
    assert d1_invalid == [] and d1_mitigated == []
    h4 = phantom_scan._active_obs("T", [_ob("4h")], healthy)
    assert len(h4) == 1 and h4[0]["state"] == "FRESH"

    stacked = orderblocks.stack_obs(d1_invalid, h4, [])
    assert stacked[0]["stack_count"] == 1, stacked
    d1_live = phantom_scan._active_obs("T", [_ob("1day")], healthy)
    assert orderblocks.stack_obs(d1_live, h4, [])[0]["stack_count"] == 2
    print("Geçersiz/mitigate OB stacking'e girmiyor, canlı OB giriyor: GEÇTİ")
    print("test_step19: OK")


if __name__ == "__main__":
    main()
