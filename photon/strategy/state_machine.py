"""FINAL_SPEC §17 durum makinesi. Kurulum (Setup) düzeyi: WATCHING → … → CLOSED; küresel düzey: IDLE/MAPPING/WATCHING/DAY_LOCKED.

Geçişler tablo ile doğrulanır; yasa dışı geçiş IllegalTransition fırlatır. Geçmiş (neden + zaman) her kurulumda tutulur."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from ..structure.models import StructureEvent, Trend
from ..zones.models import Zone


class State(str, Enum):
    IDLE = "IDLE"
    MAPPING = "MAPPING"
    WATCHING = "WATCHING"
    POI_MITIGATED = "POI_MITIGATED"
    CONFIRMATION_PENDING = "CONFIRMATION_PENDING"
    ENTRY_READY = "ENTRY_READY"
    ORDER_PENDING = "ORDER_PENDING"
    POSITION_OPEN = "POSITION_OPEN"
    RISK_FREE = "RISK_FREE"
    CLOSED = "CLOSED"
    DAY_LOCKED = "DAY_LOCKED"


S = State
ALLOWED: dict[State, frozenset[State]] = {
    S.IDLE: frozenset({S.MAPPING}),
    S.MAPPING: frozenset({S.WATCHING, S.IDLE}),
    S.WATCHING: frozenset({S.POI_MITIGATED, S.IDLE, S.DAY_LOCKED}),
    S.POI_MITIGATED: frozenset({S.WATCHING, S.CONFIRMATION_PENDING}),
    S.CONFIRMATION_PENDING: frozenset({S.ENTRY_READY, S.WATCHING}),
    S.ENTRY_READY: frozenset({S.ORDER_PENDING, S.WATCHING}),
    S.ORDER_PENDING: frozenset({S.POSITION_OPEN, S.WATCHING}),
    S.POSITION_OPEN: frozenset({S.RISK_FREE, S.CLOSED}),
    S.RISK_FREE: frozenset({S.CLOSED}),
    S.CLOSED: frozenset({S.WATCHING, S.DAY_LOCKED}),
    S.DAY_LOCKED: frozenset({S.IDLE}),
}
ACTIVE_ORDER_STATES = frozenset({S.ORDER_PENDING, S.POSITION_OPEN, S.RISK_FREE})


class IllegalTransition(RuntimeError):
    pass


@dataclass(frozen=True)
class Rejection:
    time: datetime
    reason: str          # örn. SL_BELOW_MIN, GATE:range_filter, DUPLICATE_POI, NO_ENTRY_ZONE
    rule: str = ""
    detail: str = ""


@dataclass
class Setup:
    """FINAL_SPEC §24 Setup. Kimlik: (parite, POI TF, zon id, yön)."""
    id: str
    pair: str
    poi: Zone
    direction: Trend
    state: State = State.WATCHING
    history: list[tuple[datetime, State, State, str]] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    mitigated_zone: Optional[Zone] = None        # dokunulan zon (4H POI'de rafine M15 zonu)
    visit_start: Optional[int] = None            # M1 dizisinde mevcut dokunuşun ilk mumu
    mitigation_time: Optional[datetime] = None
    choch: Optional[StructureEvent] = None
    liquidation: Any = None                      # mitigasyon anında hesaplanan LiquidationResult (EN-R001 adım 1)
    entry_zone: Optional[Zone] = None
    entry_zone_kind: str = ""                    # FLIP | EXTREME | POI (RISK girişi)
    intent: Any = None                           # OrderIntent
    has_inducement: Optional[bool] = None        # alarm anında hesaplanır (LQ-R003)
    cancelled: Optional[str] = None              # kalıcı iptal nedeni (POI geçersiz)
    notes: list[str] = field(default_factory=list)

    def to(self, new: State, time: datetime, reason: str = "") -> None:
        if new not in ALLOWED[self.state]:
            raise IllegalTransition(f"{self.state.value} → {new.value} yasak ({self.id})")
        self.history.append((time, self.state, new, reason))
        self.state = new

    def reject(self, time: datetime, reason: str, rule: str = "", detail: str = "") -> None:
        self.rejections.append(Rejection(time, reason, rule, detail))

    @property
    def active_order(self) -> bool:
        return self.state in ACTIVE_ORDER_STATES


def global_state(now_in_session: bool, day_locked: bool, n_active_pois: int) -> State:
    """Küresel durum (§17): gün kilitli → DAY_LOCKED; seans dışı → IDLE; seans içi POI yoksa MAPPING, varsa WATCHING."""
    if day_locked:
        return State.DAY_LOCKED
    if not now_in_session:
        return State.IDLE
    return State.WATCHING if n_active_pois > 0 else State.MAPPING
