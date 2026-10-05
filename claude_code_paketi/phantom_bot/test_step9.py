"""Adım 9 örnek setup puanlama gösterimi."""
import scoring


def print_result(name, setup):
    result = scoring.score_setup(setup)
    print("{}: {} puan — not {} (ham {})".format(name, result["score"], result["grade"], result["raw_score"]))
    for item in result["breakdown"]:
        print("  {:+d} — {}".format(item["points"], item["label"]))
    return result


def main():
    strong = {
        "direction": "BULLISH", "htf_bias_d1": "BULLISH", "htf_bias_h4": "BULLISH",
        "stack_count": 3, "poi_state": "FRESH", "ob_label": "EXTREME",
        "sweep": True, "bos_after_sweep": True, "mitigated_left_zone": True,
        "fvg": True, "major_structure_break": True, "inducement": True,
        "premium_discount": True, "corrective_return": True, "session_tag": "NYAM",
    }
    weak = {
        "direction": "BEARISH", "htf_bias_d1": "BULLISH", "htf_bias_h4": "BULLISH",
        "stack_count": 1, "poi_state": "TAPPED", "v_reversal": True,
        "asia": True, "news": True, "counter_trend": True,
    }
    strong_result = print_result("Güçlü setup", strong)
    weak_result = print_result("Zayıf setup", weak)
    assert strong_result["score"] > weak_result["score"]
    assert strong_result["grade"] in ("A", "B")
    assert weak_result["grade"] == "-"
    print("test_step9: OK")


if __name__ == "__main__":
    main()
