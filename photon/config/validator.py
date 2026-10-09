"""Config doğrulayıcı — REQUIRED/eksik alan varsa modül başlamaz (fail-fast)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .loader import MISSING, Config, get_path, is_missing
from .schema import MODULES, PAIR, Requirement


class ConfigError(RuntimeError):
    def __init__(self, reports: list["ModuleReport"]):
        self.reports = reports
        super().__init__(format_errors(reports))


@dataclass
class ModuleReport:
    module: str
    missing: list[str] = field(default_factory=list)
    invalid: list[tuple[str, str]] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)  # bağımlı modüller

    @property
    def ok(self) -> bool:
        return not (self.missing or self.invalid or self.blocked_by)


def _expand(req: Requirement, pairs: Iterable[str]) -> list[str]:
    if PAIR not in req.path:
        return [req.path]
    return [req.path.replace(PAIR, p) for p in pairs]


def _own_report(cfg: Config, module: str) -> ModuleReport:
    rep = ModuleReport(module)
    for req in MODULES[module].requires:
        if req.when is not None and not req.when(cfg.raw):
            continue
        for path in _expand(req, cfg.pairs):
            value = get_path(cfg.raw, path)
            if is_missing(value):
                rep.missing.append(path)
            elif req.check is not None and (msg := req.check(value)) is not None:
                rep.invalid.append((path, msg))
    return rep


def validate_module(cfg: Config, module: str) -> ModuleReport:
    """Modülün kendi alanları + bağımlı modüllerinin durumu."""
    if module not in MODULES:
        raise KeyError(f"bilinmeyen modül: {module!r}; geçerli: {', '.join(MODULES)}")
    rep = _own_report(cfg, module)
    rep.blocked_by = [d for d in _closure(module) if not _own_report(cfg, d).ok]
    return rep


def _closure(module: str) -> list[str]:
    seen: list[str] = []
    stack = list(MODULES[module].depends_on)
    while stack:
        m = stack.pop()
        if m not in seen:
            seen.append(m)
            stack.extend(MODULES[m].depends_on)
    return seen


def validate_all(cfg: Config) -> dict[str, ModuleReport]:
    return {m: validate_module(cfg, m) for m in MODULES}


def format_errors(reports: list[ModuleReport]) -> str:
    lines = ["Config doğrulama başarısız — modül başlatılamaz:"]
    for r in reports:
        if r.ok:
            continue
        lines.append(f"  [{r.module}]")
        lines += [f"    eksik (REQUIRED/boş): {p}" for p in r.missing]
        lines += [f"    geçersiz: {p} -> {m}" for p, m in r.invalid]
        if r.blocked_by:
            lines.append(f"    bağımlılıklar hazır değil: {', '.join(r.blocked_by)}")
    return "\n".join(lines)


def collect_failures(cfg: Config, *modules: str) -> list[ModuleReport]:
    """Hazır olmayan modüller + hazır olmayan bağımlılıklarının raporları."""
    bad = [r for r in (validate_module(cfg, m) for m in modules) if not r.ok]
    extra: list[ModuleReport] = []
    for r in bad:
        for dep in r.blocked_by:
            d = _own_report(cfg, dep)
            if not d.ok and all(d.module != x.module for x in bad + extra):
                extra.append(d)
    return bad + extra


def require(cfg: Config, *modules: str) -> None:
    """Her modül için hazır değilse ConfigError (tüm eksikler tek mesajda)."""
    failures = collect_failures(cfg, *modules)
    if failures:
        raise ConfigError(failures)


__all__ = ["ConfigError", "ModuleReport", "validate_module", "validate_all", "require", "collect_failures", "MISSING"]
