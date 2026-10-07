"""bt_stats testleri: bootstrap, küme bootstrap, P(ort>0), en iyi k hariç ortalama."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bt_stats as bs  # noqa: E402


def main():
    # Deterministik: aynı veri + etiket → aynı sonuç; farklı etiket → farklı tohum.
    source = random.Random(1)
    values = [source.uniform(-1, 1.2) for _ in range(60)]
    a = bs.mean_ci(values, "grup-1", 500)
    assert a == bs.mean_ci(values, "grup-1", 500)
    assert a != bs.mean_ci(values, "grup-2", 500) and bs.seed_for("x") == bs.seed_for("x")

    # Hepsi pozitif → P = 1, alt sınır > 0; hepsi negatif → P = 0
    pos = bs.mean_ci([0.5, 1.0, 1.5, 2.0, 0.8, 1.2, 0.9, 1.1], "pos", 500)
    assert pos["p_pos"] == 1.0 and pos["lo"] > 0 and pos["lo"] <= pos["mean"] <= pos["hi"]
    neg = bs.mean_ci([-0.5, -1.0, -1.5, -2.0, -0.8, -1.2], "neg", 500)
    assert neg["p_pos"] == 0.0 and neg["hi"] < 0

    # Simetrik ±1: aralık 0'ı kapsar, P yaklaşık 0.5
    sym = bs.mean_ci([1.0, -1.0] * 100, "sym", 1000)
    assert sym["lo"] < 0 < sym["hi"] and 0.3 < sym["p_pos"] < 0.7, sym

    # Büyük n → dar aralık; küçük n → geniş aralık. Aralık %90 düzeyinde: kapsama kabaca %90 (Monte Carlo).
    wide = bs.mean_ci(values[:10], "w", 500)
    narrow = bs.mean_ci(values * 10, "n", 500)
    assert (wide["hi"] - wide["lo"]) > 2 * (narrow["hi"] - narrow["lo"])
    covered = 0
    for trial in range(200):
        rng = random.Random(trial)
        sample = [rng.gauss(0.3, 1.0) for _ in range(80)]
        ci = bs.mean_ci(sample, "cov-%d" % trial, 300)
        covered += ci["lo"] <= 0.3 <= ci["hi"]
    assert 0.82 <= covered / 200 <= 0.97, covered / 200

    # Yetersiz veri → aralık yok
    few = bs.mean_ci([1.0, 2.0, 3.0], "few")
    assert few["lo"] is None and few["p_pos"] is None and few["n"] == 3
    assert bs.mean_ci([], "empty")["n"] == 0

    # Küme bootstrap: gün içinde aynı yönlü (korelasyonlu) işlemlerde düz bootstrap'ten GENİŞ olmalı.
    rng = random.Random(5)
    day_effect = {day: rng.choice([-1.0, 1.0]) for day in range(30)}
    vals, clusters = [], []
    for day, effect in day_effect.items():
        for _ in range(10):
            vals.append(effect + rng.gauss(0, 0.05))
            clusters.append(day)
    iid = bs.mean_ci(vals, "c", 800)
    clustered = bs.cluster_mean_ci(vals, clusters, "c", 800)
    assert (clustered["hi"] - clustered["lo"]) > 3 * (iid["hi"] - iid["lo"]), (clustered, iid)
    assert clustered["clusters"] == 30 and clustered["n"] == 300
    # Her gün birden fazla işlem ama bağımsız gürültü → iki yöntem benzer genişlikte
    vals2 = [rng.gauss(0.2, 1.0) for _ in range(300)]
    clusters2 = [i // 10 for i in range(300)]
    iid2, cl2 = bs.mean_ci(vals2, "d", 800), bs.cluster_mean_ci(vals2, clusters2, "d", 800)
    ratio = (cl2["hi"] - cl2["lo"]) / (iid2["hi"] - iid2["lo"])
    assert 0.6 < ratio < 1.6, ratio
    # Az küme → aralık yok
    assert bs.cluster_mean_ci([1.0] * 20, [1] * 10 + [2] * 10, "few-days")["lo"] is None
    # Aynı gün anahtarı UTC gününe göre
    assert bs.day_key(86400 * 3 + 5) == 3 and bs.day_key(86400 * 3 - 1) == 2

    # En iyi k işlem hariç ortalama
    assert bs.trimmed_mean_excl_top([10, 9, 8, 7, 6, 1, 1, 1, 1, 1], 5) == 1.0
    assert bs.trimmed_mean_excl_top([1, 2, 3], 5) is None and bs.trimmed_mean_excl_top([1, 2, 3, 4, 5], 5) is None
    assert abs(bs.trimmed_mean_excl_top([5.0, 4, 3, 2, 1, 0, -1, -2], 5) - (0 - 1 - 2) / 3) < 1e-12
    print("Bootstrap, küme bootstrap, P(ort>0), kapsama ve en iyi k hariç ortalama: GEÇTİ")
    print("test_bt_stats: OK")


if __name__ == "__main__":
    main()
