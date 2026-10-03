"""Adım 32: WAITING_TAP iken süpürülmüş TP1 'TP1_PROVISIONAL' olarak işaretlenir."""
import signals
import synth


def scan_with_status(status):
    synth.isolate_dirs()
    original = signals.ltf_status

    def forced(poi, *args, **kwargs):
        result = original(poi, *args, **kwargs)
        result["status"] = status
        return result

    signals.ltf_status = forced
    try:
        return synth.scan(279)[0]
    finally:
        signals.ltf_status = original


def main():
    waiting = [c for c in scan_with_status("WAITING_TAP") if c["tp1"] is not None]
    assert waiting, "sentetik veri TP1'li aday üretmedi"
    for item in waiting:
        assert "TP1_PROVISIONAL" in item["warnings"] and "TP1_SWEPT_LEVEL" not in item["warnings"], item
    tapped = [c for c in scan_with_status("TAPPED_NO_BOS") if c["tp1"] is not None]
    assert tapped
    for item in tapped:
        assert "TP1_SWEPT_LEVEL" in item["warnings"] and "TP1_PROVISIONAL" not in item["warnings"], item
    print("WAITING_TAP: TP1_PROVISIONAL; TAPPED_NO_BOS: TP1_SWEPT_LEVEL: GEÇTİ")
    print("test_step32: OK")


if __name__ == "__main__":
    main()
