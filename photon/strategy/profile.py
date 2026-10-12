"""İcra profili (V8, T-M15BT [00:02:36]): "replacing the four hour, the m15 and the m1 with the daily, the four hour and the m15".

Strateji kodu ROL anahtarlarıyla çalışır: rol H4 = "üst TF" (EN-R006 4H trendi / 4H POI), rol M15 = "orta TF" (M15 trendi / POI TF / izin CHoCH'u),
icra = "M1" (giriş CHoCH'u, giriş kutusu, liquidation). Profil bu rolleri gerçek TF'lere eşler:
  M1  (varsayılan): D1→D1, H4→H4, M15→M15, icra M1
  M15 (V8)        : D1→—,  H4→D1, M15→H4,  icra M15
Rol sözlükleri (durum, zon listeleri, olaylar) runner tarafından bu eşlemeyle doldurulur; model/POI/yönetim kodu değişmez."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..data.models import Timeframe

D1, H4, M15, M1 = Timeframe.D1, Timeframe.H4, Timeframe.M15, Timeframe.M1


@dataclass(frozen=True)
class Profile:
    name: str
    exec_tf: Timeframe
    role_map: tuple[tuple[Timeframe, Optional[Timeframe]], ...]      # (rol, gerçek TF | None)
    hold_role: Timeframe = H4           # D-26 tutma onayı CHoCH'unun rolü (M1: "4H" rolü=H4; V8: "M15" rolü=H4 — Q-V8-5: hedefler/onay H4'te kalır)

    def real(self, role: Timeframe) -> Optional[Timeframe]:
        return dict(self.role_map)[role]

    @property
    def hi(self) -> Timeframe:          # "4H" rolü
        return self.real(H4)

    @property
    def mid(self) -> Timeframe:         # "M15" rolü
        return self.real(M15)

    @property
    def hold_tf(self) -> Timeframe:
        return self.real(self.hold_role)

    @property
    def poi_tfs(self) -> tuple[Timeframe, ...]:
        return tuple(r for _, r in self.role_map if r is not None)

    @property
    def refine_min_tf(self) -> Timeframe:
        """D-02 / "4H POI" rolü: bu TF ve üstündeki POI'de rafine zon beklenir / fiyat 4H POI'de sayılır."""
        return self.hi


PROFILES = {
    "M1": Profile("M1", M1, ((D1, D1), (H4, H4), (M15, M15))),
    "M15": Profile("M15", M15, ((D1, None), (H4, D1), (M15, H4)), M15),
}


def profile_from_config(cfg) -> Profile:
    name = cfg.get("execution_profile") or "M1"             # config'te anahtar yok → mevcut M1 modeli
    if name not in PROFILES:
        raise ValueError(f"bilinmeyen execution_profile {name!r}; geçerli: {sorted(PROFILES)}")
    return PROFILES[name]
