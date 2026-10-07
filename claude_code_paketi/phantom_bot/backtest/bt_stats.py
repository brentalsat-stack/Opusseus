"""Bootstrap güven aralıkları (düz ve gün bazlı küme), P(ort>0) ve en iyi k işlem hariç ortalama.

Yalnızca standart kütüphane. Tohum, grup etiketinden türetilir: aynı veri + aynı etiket → aynı sonuç.
"""
import os
import random
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402

MIN_N = 5  # bundan az gözlemde aralık hesaplanmaz


def seed_for(label):
    return zlib.crc32(str(label).encode("utf-8"))


def _n_boot(n_boot):
    return int(config.BT_BOOTSTRAP_N if n_boot is None else n_boot)


def boot_means(values, label, n_boot=None):
    """Düz bootstrap: ``values`` bağımsız gözlem sayılır. Dönüş: bootstrap ortalamaları listesi."""
    n = len(values)
    if n == 0:
        return []
    rng = random.Random(seed_for(label))
    choices = rng.choices
    return [sum(choices(values, k=n)) / n for _ in range(_n_boot(n_boot))]


def cluster_boot_means(values, clusters, label, n_boot=None):
    """Küme bootstrap'i: kümeler (ör. UTC günü) yerine koymayla çekilir; ortalama = toplam / toplam adet."""
    sums, counts = {}, {}
    for value, cluster in zip(values, clusters):
        sums[cluster] = sums.get(cluster, 0.0) + value
        counts[cluster] = counts.get(cluster, 0) + 1
    keys = sorted(sums)
    if not keys:
        return []
    cluster_sums = [sums[key] for key in keys]
    cluster_counts = [counts[key] for key in keys]
    size = len(keys)
    rng = random.Random(seed_for(label))
    means = []
    for _ in range(_n_boot(n_boot)):
        picks = rng.choices(range(size), k=size)
        total_count = sum(cluster_counts[i] for i in picks)
        means.append(sum(cluster_sums[i] for i in picks) / total_count)
    return means


def summarize(means, level=None):
    """Bootstrap ortalamalarından {lo, hi, p_pos}; yeterli veri yoksa None değerler."""
    if not means:
        return {"lo": None, "hi": None, "p_pos": None}
    level = config.BT_BOOTSTRAP_LEVEL if level is None else level
    ordered = sorted(means)
    size = len(ordered)
    tail = (1.0 - level) / 2.0
    lo = ordered[min(size - 1, int(tail * size))]
    hi = ordered[max(0, min(size - 1, int((1.0 - tail) * size) - 1))]
    return {"lo": lo, "hi": hi, "p_pos": sum(1 for m in ordered if m > 0) / size}


def mean_ci(values, label, n_boot=None):
    """Düz bootstrap özeti: {n, mean, lo, hi, p_pos}. n < MIN_N için aralık None."""
    n = len(values)
    result = {"n": n, "mean": sum(values) / n if n else 0.0, "lo": None, "hi": None, "p_pos": None}
    if n >= MIN_N:
        result.update(summarize(boot_means(values, label, n_boot)))
    return result


def cluster_mean_ci(values, clusters, label, n_boot=None):
    """Küme bootstrap özeti: {n, clusters, mean, lo, hi, p_pos}. Küme sayısı < MIN_N için aralık None."""
    n = len(values)
    distinct = len(set(clusters))
    result = {"n": n, "clusters": distinct, "mean": sum(values) / n if n else 0.0,
              "lo": None, "hi": None, "p_pos": None}
    if n >= MIN_N and distinct >= MIN_N:
        result.update(summarize(cluster_boot_means(values, clusters, label, n_boot)))
    return result


def trimmed_mean_excl_top(values, k=5):
    """En yüksek k değer çıkarılınca ortalama; n <= k ise None."""
    if len(values) <= k:
        return None
    ordered = sorted(values)
    return sum(ordered[:-k]) / (len(ordered) - k)


def day_key(timestamp):
    """UTC gün numarası (küme anahtarı)."""
    return int(timestamp // 86400)
