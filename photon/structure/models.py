"""Yapı veri yapıları (FINAL_SPEC §6, §24)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from ..data.models import Timeframe


class Trend(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    UNDEFINED = "UNDEFINED"  # başlangıç: cold start kaynakta tanımsız (U-15); motor Seed olmadan olay üretmez

    @property
    def opposite(self) -> "Trend":
        return {Trend.BULL: Trend.BEAR, Trend.BEAR: Trend.BULL}[self]


class EventType(str, Enum):
    CHOCH = "CHoCH"                       # MS-R005
    BOS = "BOS"                           # MS-R006 / MS-R009 (trend değişimi bearish/bullish BOS)
    SWING_CONFIRMED = "SWING_CONFIRMED"   # MS-R008 (bilgi amaçlı; kural olayı değil)
    INTERNAL_REF = "INTERNAL_REF"         # MS-R003 yeni internal referans (bilgi amaçlı)
    OUTSIDE_BAR = "OUTSIDE_BAR"           # Q-S04: sırası çözülemeyen mum — SİNYAL ÜRETMEZ


class Strength(str, Enum):
    STRONG = "STRONG"
    WEAK = "WEAK"


class Kind(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


@dataclass(frozen=True)
class SwingPoint:
    tf: Timeframe
    price: Decimal
    index: int
    kind: Kind
    strength: Strength
    confirmed: bool


@dataclass(frozen=True)
class StructureEvent:
    tf: Timeframe
    type: EventType
    dir: Trend                  # BULL / BEAR
    level: Decimal              # kırılan seviye (SWING_CONFIRMED/INTERNAL_REF için ilgili seviye)
    break_index: int
    time: datetime              # olayı doğuran mumun open_time (UTC)
    by_close: bool
    ref: Optional[SwingPoint] = None
    note: str = ""              # örn. "OUTSIDE_BAR_RESOLVED" (Q-S04)
    rule: str = ""              # kural ID'si
    warmup: bool = False        # True: warm-up döneminde oluştu → yalnızca yapıyı kurar, sinyal üretmez (Q-S01)
    level_index: Optional[int] = None    # kırılan seviyenin oluştuğu mum indeksi
    origin_index: Optional[int] = None   # kırılımı yapan hareketin başladığı uç mumu (BOS: kutu ucu; CHoCH: pullback başlangıcı) — zon→BOS bağlaması (SD-R005)

    @property
    def signal_capable(self) -> bool:
        """Strateji katmanı yalnızca bunlara bakar: warm-up dışı CHoCH/BOS (OUTSIDE_BAR hiçbir zaman sinyal değildir)."""
        return not self.warmup and self.type in (EventType.CHOCH, EventType.BOS)


@dataclass(frozen=True)
class InternalRef:
    price: Decimal
    index: int


@dataclass(frozen=True)
class MarketState:
    tf: Timeframe
    swing_trend: Trend
    swing_high: Optional[SwingPoint]
    swing_low: Optional[SwingPoint]
    internal_trend: Trend
    internal_high: Optional[InternalRef]   # bearish iç yapıda geçerli CHoCH referansı
    internal_low: Optional[InternalRef]    # bullish iç yapıda geçerli CHoCH referansı
    eq: Optional[Decimal]                  # FM-08 / PD-R001: low + 0.5 * (high - low)


@dataclass(frozen=True)
class Seed:
    """Cold start (U-15) kaynakta tanımsız → başlangıç durumu kullanıcı tarafından AÇIKÇA verilir.
    İndeksler `history` listesindeki mum sırasıdır (0 tabanlı)."""
    swing_trend: Trend
    swing_high_index: int
    swing_low_index: int
    swing_high_confirmed: bool          # trendin yönündeki uç (BULL'da high, BEAR'da low) onaylı mı
    internal_trend: Trend
    internal_ref_index: int             # internal_trend BULL: referans low'un, BEAR: referans high'ın mum indeksi


@dataclass(frozen=True)
class Diagnostic:
    """Q-S03 vb. belgelenmiş köşe durumlar (olay değil; sinyali etkilemez)."""
    kind: str            # "Q-S03a" (aday internal low yok) | "Q-S03b" (CHoCH sonrası aday internal high yok)
    index: int
    time: datetime
    detail: str
