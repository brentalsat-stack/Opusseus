"""config.yaml yükleme. Hiçbir alana varsayılan değer atanmaz."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import yaml

from .schema import REQUIRED

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config.yaml"
MISSING = object()


def _decimalize(node: Any) -> Any:
    """YAML float -> Decimal (float yok; fiyat/pip değerleri Decimal)."""
    if isinstance(node, float):
        return Decimal(repr(node))
    if isinstance(node, dict):
        return {k: _decimalize(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_decimalize(v) for v in node]
    return node


def get_path(raw: Mapping[str, Any], path: str) -> Any:
    """Noktalı yol; yoksa MISSING."""
    node: Any = raw
    for key in path.split("."):
        if not isinstance(node, Mapping) or key not in node:
            return MISSING
        node = node[key]
    return node


def is_missing(value: Any) -> bool:
    return (value is MISSING or value is None
            or (isinstance(value, str) and value.strip() in ("", REQUIRED)))


def find_required(raw: Any, prefix: str = "") -> list[str]:
    """Ağaçtaki tüm REQUIRED/boş yaprakların yolları."""
    out: list[str] = []
    if isinstance(raw, Mapping):
        for k, v in raw.items():
            out += find_required(v, f"{prefix}{k}.")
    elif is_missing(raw):
        out.append(prefix.rstrip("."))
    return out


class Config:
    def __init__(self, raw: Mapping[str, Any], path: Path | None = None):
        self.raw = raw
        self.path = path

    def get(self, path: str, default: Any = None) -> Any:
        v = get_path(self.raw, path)
        return default if v is MISSING else v

    @property
    def pairs(self) -> tuple[str, ...]:
        return tuple(self.raw.get("pairs") or ())

    def pip_size(self, pair: str) -> Decimal:
        return Decimal(str(self.raw["pair_params"][pair]["pip_size"]))

    def swing_min_pullback_pips(self, pair: str, tf: str) -> Decimal:
        return Decimal(str(self.raw["swing_min_pullback_pips"][pair][tf]))

    def require(self, *modules: str) -> None:
        """Eksik/geçersiz varsa ConfigError fırlatır (fail-fast)."""
        from .validator import require
        require(self, *modules)


def load_config(path: str | Path = DEFAULT_PATH) -> Config:
    p = Path(path)
    with p.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"{p}: kök düğüm bir eşleme (mapping) olmalı")
    return Config(_decimalize(raw), p)
