"""Trend hizalama → execution izin matrisi (EN-R006) ve pro/karşı trend sınıflaması (DECISIONS §5). Saf fonksiyonlar.

Tablo (FINAL_SPEC §4 / RULE_DATABASE EN-R006):
  PRO/PRO         → M15+ POI mitigasyonunda M1 modeli serbest
  PRO/COUNTER     → (a) önce M15 CHoCH (→ PRO/PRO) veya (b) fiyat 4H POI'yi mitige ettiyse
  COUNTER/COUNTER → işlem yok; M15 CHoCH beklenir (sonra COUNTER/PRO satırı)
  COUNTER/PRO     → HTF (≥M15) POI içinde M1 modeli serbest
`m15_choch_toward_dir`: çağıranın sağladığı bayrak (Q-P1: kaynak "M15 CHoCH"un nasıl türetileceğini tanımlamıyor).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..structure.models import Trend


class TrendClass(str, Enum):
    PRO = "PRO"                  # 4H ve M15 ikisi de işlem yönünde (DECISIONS: pro-trend)
    COUNTER_HTF = "COUNTER_HTF"  # 4H'ye karşı her işlem (DECISIONS: karşı trend)
    MIXED = "MIXED"              # 4H işlem yönünde, M15 karşı — DECISIONS'ta sınıf yok (Q-P6)


def classify_trend(trend_4h: Trend, trend_m15: Trend, direction: Trend) -> TrendClass:
    _check(direction)
    if trend_4h is Trend.UNDEFINED or trend_m15 is Trend.UNDEFINED:
        raise ValueError("trend tanımsız")
    if trend_4h is not direction:
        return TrendClass.COUNTER_HTF
    return TrendClass.PRO if trend_m15 is direction else TrendClass.MIXED


def _check(direction: Trend) -> None:
    if direction not in (Trend.BULL, Trend.BEAR):
        raise ValueError("işlem yönü BULL veya BEAR olmalı")


@dataclass(frozen=True)
class Permission:
    allowed: bool
    row: str                 # örn. "PRO/COUNTER"
    reason: str
    rule: str = "EN-R006"


def check_permission(trend_4h: Trend, trend_m15: Trend, direction: Trend, *, price_in_htf_poi: bool,
                     price_in_4h_poi: bool, m15_choch_toward_dir: bool = False) -> Permission:
    """EN-R006. `price_in_htf_poi`: fiyat ≥M15 bir POI'yi mitige etti; `price_in_4h_poi`: 4H POI'yi mitige etti."""
    _check(direction)
    if trend_4h is Trend.UNDEFINED or trend_m15 is Trend.UNDEFINED:
        return Permission(False, "UNDEFINED", "TREND_UNDEFINED: yapı henüz kurulmadı (warm-up)")
    pro4 = trend_4h is direction
    pro15 = trend_m15 is direction
    row = f"{'PRO' if pro4 else 'COUNTER'}/{'PRO' if pro15 else 'COUNTER'}"
    if not pro15 and m15_choch_toward_dir:
        pro15 = True      # M15 CHoCH işlem yönüne döndü → satır PRO/PRO veya COUNTER/PRO olur
        row += "→CHoCH"
    if pro4 and pro15:
        return (Permission(True, row, "PRO/PRO: M15+ POI mitigasyonunda M1 modeli serbest") if price_in_htf_poi else
                Permission(False, row, "PRO/PRO ama fiyat ≥M15 POI içinde değil"))
    if pro4 and not pro15:
        return (Permission(True, row, "PRO/COUNTER: fiyat 4H POI'yi mitige etti") if price_in_4h_poi else
                Permission(False, row, "PRO/COUNTER: M15 CHoCH bekle veya 4H POI mitigasyonu gerekli"))
    if not pro4 and pro15:
        return (Permission(True, row, "COUNTER/PRO: HTF (≥M15) POI içinde M1 modeli serbest") if price_in_htf_poi else
                Permission(False, row, "COUNTER/PRO ama fiyat ≥M15 POI içinde değil"))
    return Permission(False, row, "COUNTER/COUNTER: işlem yok, M15 CHoCH bekle")
