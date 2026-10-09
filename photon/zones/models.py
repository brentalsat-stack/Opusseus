"""Zon veri yapıları (FINAL_SPEC §24, SD-R001..R007)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from ..data.models import Timeframe
from ..structure.models import EventType, StructureEvent, Trend


class ZoneKind(str, Enum):
    DEMAND = "DEMAND"    # kopuş yukarı (SD-R003)
    SUPPLY = "SUPPLY"

    @property
    def direction(self) -> Trend:
        return Trend.BULL if self is ZoneKind.DEMAND else Trend.BEAR

    @property
    def opposite(self) -> "ZoneKind":
        return ZoneKind.SUPPLY if self is ZoneKind.DEMAND else ZoneKind.DEMAND


class Origin(str, Enum):
    PIVOT = "PIVOT"      # STB / BTS (SD-R002)
    RANGE = "RANGE"      # ≥3 mum inside-bar zinciri (SD-R001, kullanıcı tanımı)
    FLIP = "FLIP"        # failed reaction sonrası reaksiyon kutusu (SD-R006, EN-R009)


class Context(str, Enum):
    CONTINUATION = "CONTINUATION"   # zondan önceki yön zonla aynı (SD-R003)
    REVERSAL = "REVERSAL"


@dataclass
class Zone:
    id: str
    tf: Timeframe
    kind: ZoneKind
    origin: Origin
    draw: str                        # "RANGE" (tüm koşu/zincir) | "CANDLE" (tek mum) | "REACTION" (flip kutusu)
    top: Decimal
    bottom: Decimal
    first_index: int                 # zonu oluşturan ilk mum
    created_index: int               # zonun bilindiği (kopuş / FR) mum
    created_time: datetime
    context: Optional[Context] = None
    caused_events: list[StructureEvent] = field(default_factory=list)
    is_flip: bool = False
    flipped_from: Optional[str] = None
    is_sweep: Optional[bool] = None          # LQ-R002 (oluşurken hesaplanır; None = bilinmiyor)
    mitigated_index: Optional[int] = None    # ilk dokunuş (DERIVED: zona dokunma)
    invalidated_index: Optional[int] = None  # karşı uçtan KAPANIŞLA geçildi
    flipped_index: Optional[int] = None      # bu zon failed reaction ile çevrildi (SD-R006)
    fulfilled_index: Optional[int] = None    # tepki hedefi kırıldı → görevini yaptı
    warmup: bool = False

    @property
    def valid(self) -> bool:
        """SD-R005: zon bir yapı kırılımına neden oldu VEYA flip zonu."""
        return bool(self.caused_events) or self.is_flip

    @property
    def caused_event(self) -> Optional[StructureEvent]:
        """En önemli neden: swing BOS > internal kırılım (SD-R005 önem sırası)."""
        if not self.caused_events:
            return None
        return next((e for e in self.caused_events if e.type is EventType.BOS), self.caused_events[0])

    @property
    def caused_swing_bos(self) -> bool:
        return any(e.type is EventType.BOS for e in self.caused_events)

    @property
    def eq(self) -> Decimal:
        return (self.top + self.bottom) / 2

    @property
    def distal(self) -> Decimal:
        """Fiyatın ilk dokunduğu dış kenar: talepte üst, arzda alt."""
        return self.top if self.kind is ZoneKind.DEMAND else self.bottom

    @property
    def usable(self) -> bool:
        return self.invalidated_index is None and self.flipped_index is None
