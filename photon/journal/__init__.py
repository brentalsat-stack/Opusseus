"""Journal (FINAL_SPEC §22, §24): işlem etiketi VALID/INVALID × WIN/LOSS."""
from __future__ import annotations


def journal_tag(valid_by_plan: bool, win: bool) -> str:
    """Trade.journal_tag. `valid_by_plan`: işlem, plan kapılarından (SD-R005, PD-R003, EN-R006, seans, liquidation, MG-R005) geçti mi."""
    return f"{'VALID' if valid_by_plan else 'INVALID'}_{'WIN' if win else 'LOSS'}"
