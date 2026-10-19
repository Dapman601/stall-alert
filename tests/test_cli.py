from stall_alert.cli import classify_fallback_causes


def test_classify_invented_duration_as_flagged_duration():
    causes = classify_fallback_causes("validation failed: invented duration '2 days'")
    assert "flagged_duration" in causes
    assert "other" not in causes


def test_classify_unknown_reason_falls_back_to_other():
    causes = classify_fallback_causes("validation failed: something unrecognized")
    assert causes == ["other"]
