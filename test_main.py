from main import translate


def test_threshold_with_current():
    raw = "CPU on 七牛香港-主控 exceeded 85% (current: 92.3%)"
    result = translate(raw)
    assert "七牛香港-主控" in result
    assert "92.3%" in result
    assert "85%" in result
    assert "CPU 使用率" in result


def test_node_down():
    result = translate("云悠HK is down")
    assert "离线" in result
    assert "云悠HK" in result


def test_node_up():
    result = translate("云悠HK is up")
    assert "恢复" in result
    assert "云悠HK" in result


def test_fallback():
    result = translate("{empty}")
    assert "Beszel 告警" in result


def test_metric_translation():
    cases = [
        ("Memory on srv exceeded 90% (current: 91%)", "内存使用率"),
        ("Disk on srv exceeded 80% (current: 82%)", "磁盘使用率"),
        ("Temperature on srv exceeded 75% (current: 76%)", "温度"),
    ]
    for raw, expected_zh in cases:
        assert expected_zh in translate(raw), f"Missing '{expected_zh}' for: {raw}"


def test_pattern_d():
    result = translate("Disk exceeded 80% on 云悠HK")
    assert "云悠HK" in result
    assert "磁盘使用率" in result
