"""Adım 34: 'Diğer adaylar' — A/B tablosuna girmeyen actionable rank 2+ adaylar."""
from datetime import datetime, timezone

import report
import synth
from test_step33 import row, section


def main():
    synth.isolate_dirs()
    results = [
        row("MOVRUSDT", "crypto", 100.0, 101.0, score=87, rank=1),           # A/B tablosu
        row("MOVRUSDT", "crypto", 98.0, 101.0, score=81, rank=2),            # A, R:R iyi → Diğer
        row("MOVRUSDT", "crypto", 97.0, 101.0, score=50, rank=3, grade="C"),  # C → izleme (Diğer'de tekrar yok)
        row("NIGHTUSDT", "crypto", 100.0, 101.0, score=70, rank=1, rr=8.0),   # rapor sıralaması: rank 1 → A/B
        row("NIGHTUSDT", "crypto", 95.0, 101.0, score=62, rank=2, rr=8.0),    # B, R:R iyi, rank 2 → Diğer
        row("NIGHTUSDT", "crypto", 94.0, 101.0, score=61, rank=3, rr=2.0),    # R:R düşük → izleme
        row("FARUSDT", "crypto", 100.0, 200.0, score=90, rank=2),            # uzak → yalnız Uzak POI'ler
        row("LOWUSDT", "crypto", 100.0, 101.0, score=30, rank=2),            # eşik altı → hiçbir yerde
    ]
    for item in results:
        item.setdefault("grade", "A" if item["score"] >= 75 else "B" if item["score"] >= 60 else
                        "C" if item["score"] >= 45 else "-")
        item["poi_proximal"] = item["entry"]
    # Aynı sembolde farklı bölgeler farklı aday anahtarı üretsin.
    meta = {"scan_time_utc": datetime(2026, 10, 3, tzinfo=timezone.utc), "market": "crypto",
            "symbols_scanned": 4, "duration_seconds": 1, "error_count": 0, "errors": [], "symbols": [],
            "show_all": True}
    paths = report.write_reports(results, meta)
    markdown = open(paths["md"], encoding="utf-8").read()
    ab, watch, other, far = (section(markdown, "A/B setup"), section(markdown, "İzleme listesi"),
                             section(markdown, "Diğer adaylar"), section(markdown, "Uzak POI"))
    assert ab.count("MOVRUSDT") == 1 and "| 87 |" in ab and "| 70 |" in ab
    assert "| 61 |" in watch and "| 50 |" in watch
    assert other.count("MOVRUSDT") == 1 and "| 81 |" in other, other
    assert other.count("NIGHTUSDT") == 1 and "| 62 |" in other, other
    assert "| 50 |" not in other and "FARUSDT" not in other and "LOWUSDT" not in other
    assert "FARUSDT" in far
    # Hiçbir aday iki bölümde birden görünmez.
    for score in ("| 87 |", "| 81 |", "| 61 |", "| 70 |", "| 62 |", "| 50 |"):
        assert sum(score in part for part in (ab, watch, other, far)) == 1, score
    print("Diğer adaylar: rank 2+ A/B tablosuna girmeyenler, tekrarsız: GEÇTİ")
    print("test_step34: OK")


if __name__ == "__main__":
    main()
