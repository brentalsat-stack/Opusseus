"""Config-driven Phantom SMC setup score and grade."""
import config


_LABELS = {
    "htf_alignment": "HTF yön uyumu",
    "stack_3tf": "3 TF OB çakışması",
    "stack_2tf": "2 TF OB çakışması",
    "stack_1tf": "1 TF OB",
    "fresh_ob": "Dokunulmamış OB",
    "extreme_ob": "EXTREME OB",
    "sweep_then_bos": "Sweep sonrası BOS",
    "mitigated_left_zone": "Soldaki S/D veya OB mitigation",
    "fvg": "Bacakta FVG",
    "major_structure_break": "Majör yapı kırılımı",
    "inducement": "POI önünde inducement",
    "premium_discount": "Doğru premium/discount tarafı",
    "corrective_return": "Corrective dönüş",
    "preferred_session": "London/NY teyit seansı",
    "v_reversal_penalty": "V dönüşü cezası",
    "asia_confirmation_penalty": "Asya teyidi cezası",
    "news_penalty": "Haber penceresi cezası",
    "counter_trend_penalty": "Karşı-trend cezası",
}


def _truth(setup, key, aliases=()):
    for name in (key,) + tuple(aliases):
        if name in setup:
            value = setup[name]
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "y", "evet", "same", "aligned")
            return bool(value)
    return False


def _criteria(setup):
    """Resolve raw setup attributes to the named boolean/stack criteria."""
    if "stack_count" in setup:
        stack_count = int(setup.get("stack_count") or 0)
    elif "poi_stack" in setup:
        raw = setup["poi_stack"]
        stack_count = int(raw) if isinstance(raw, (int, float)) else len(raw) if isinstance(raw, (list, tuple, set)) else 0
    else:
        stack_count = 0

    if "htf_alignment" in setup:
        htf_aligned = _truth(setup, "htf_alignment")
    else:
        direction = str(setup.get("direction", "")).upper()
        biases = [str(setup.get(key, "")).upper() for key in ("htf_bias_d1", "htf_bias_h4")]
        htf_aligned = bool(direction and len(biases) == 2 and all(bias in (direction, "BULLISH" if direction in ("LONG", "BUY") else "BEARISH" if direction in ("SHORT", "SELL") else direction) for bias in biases))

    session_tags = setup.get("session_tag", setup.get("session_tags", []))
    if isinstance(session_tags, str):
        session_tags = [tag.strip().upper() for tag in session_tags.replace(";", ",").split(",")]
    else:
        session_tags = [str(tag).upper() for tag in session_tags]
    preferred_session = _truth(setup, "preferred_session") or any(tag in ("LNDN", "NYAM", "NYPM") for tag in session_tags)
    asia = _truth(setup, "asia_confirmation_penalty", ("asia", "in_asia")) or "ASIA" in session_tags

    return {
        "htf_alignment": htf_aligned,
        "stack_3tf": stack_count >= 3,
        "stack_2tf": stack_count == 2,
        "stack_1tf": stack_count == 1,
        "fresh_ob": _truth(setup, "fresh_ob", ("poi_fresh",)) or str(setup.get("poi_state", "")).upper() == "FRESH",
        "extreme_ob": _truth(setup, "extreme_ob") or str(setup.get("ob_label", setup.get("label", ""))).upper() == "EXTREME",
        "sweep_then_bos": _truth(setup, "sweep_then_bos", ("sweep",)) and _truth(setup, "bos_after_sweep", ("bos",)),
        "mitigated_left_zone": _truth(setup, "mitigated_left_zone", ("left_zone_mitigated",)),
        "fvg": _truth(setup, "fvg", ("has_fvg",)),
        "major_structure_break": _truth(setup, "major_structure_break", ("major_bos",)),
        "inducement": _truth(setup, "inducement", ("has_inducement",)),
        "premium_discount": _truth(setup, "premium_discount", ("correct_premium_discount",)),
        "corrective_return": _truth(setup, "corrective_return", ("corrective",)),
        "preferred_session": preferred_session,
        "v_reversal_penalty": _truth(setup, "v_reversal_penalty", ("v_reversal",)),
        "asia_confirmation_penalty": asia,
        "news_penalty": _truth(setup, "news_penalty", ("news", "in_news_window")),
        "counter_trend_penalty": _truth(setup, "counter_trend_penalty", ("counter_trend",)),
    }


def score_setup(setup):
    """Return score (0–100), grade and a report-ready points breakdown.

    ``setup`` is a dictionary of booleans/attributes. Stack count is read from
    ``stack_count`` or ``poi_stack``. Weights and grade thresholds are read
    from config; overlapping stack bands are mutually exclusive.
    """
    if not isinstance(setup, dict):
        raise TypeError("setup dict olmalı")
    weights = config.SCORE_WEIGHTS
    criteria = _criteria(setup)
    breakdown = []
    raw_score = 0
    for key, enabled in criteria.items():
        weight = int(weights.get(key, 0))
        points = weight if enabled else 0
        raw_score += points
        if enabled:
            breakdown.append({"criterion": key, "label": _LABELS.get(key, key), "points": points})
    score = max(0, min(int(config.SCORE_MAX), raw_score))
    if score >= int(config.SCORE_GRADE_A):
        grade = "A"
    elif score >= int(config.SCORE_GRADE_B):
        grade = "B"
    elif score >= int(config.SCORE_GRADE_C):
        grade = "C"
    else:
        grade = "-"
    return {"score": score, "grade": grade, "raw_score": raw_score,
            "breakdown": breakdown,
            "criteria": {key: bool(value) for key, value in criteria.items()}}
