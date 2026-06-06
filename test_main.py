import pytest
from main import translate, extract_duration, extract_url, _last_sent


@pytest.fixture(autouse=True)
def clear_silence_window():
    _last_sent.clear()
    yield
    _last_sent.clear()


def test_real_beszel_disk_alert():
    raw = (
        "云悠HK disk usage above threshold\n"
        "Disk usage averaged 94.43% for the previous 1 minute.\n\n"
        "https://monitor.treesir.pub/system/gf6bzpi6976sh3c"
    )
    result = translate(raw)
    assert "🚨 告警" in result
    assert "云悠HK" in result
    assert "磁盘使用率" in result
    assert "94.43%" in result
    assert "超过阈值" in result
    assert "已持续 1 分钟" in result
    assert "详情：https://monitor.treesir.pub/system/gf6bzpi6976sh3c" in result


def test_real_beszel_cpu_alert():
    raw = (
        "七牛香港-主控 cpu usage above threshold\n"
        "Cpu usage averaged 87.5% for the previous 5 minutes.\n\n"
        "https://monitor.treesir.pub/system/lcfre2r7zvyi3tb"
    )
    result = translate(raw)
    assert "🚨 告警" in result
    assert "七牛香港-主控" in result
    assert "CPU 使用率" in result
    assert "87.5%" in result
    assert "已持续 5 分钟" in result
    assert "详情：https://monitor.treesir.pub/system/lcfre2r7zvyi3tb" in result


def test_node_down():
    raw = "云悠HK is down\n\nhttps://monitor.treesir.pub/system/gf6bzpi6976sh3c"
    result = translate(raw)
    assert "🔴 节点离线" in result
    assert "云悠HK" in result
    assert "已离线" in result
    assert "详情：https://monitor.treesir.pub" in result


def test_node_up():
    raw = "云悠HK is up\n\nhttps://monitor.treesir.pub/system/gf6bzpi6976sh3c"
    result = translate(raw)
    assert "✅ 节点恢复" in result
    assert "已恢复在线" in result


def test_silence_window_suppresses_duplicate():
    raw = (
        "云悠HK disk usage above threshold\n"
        "Disk usage averaged 94.43% for the previous 1 minute.\n\n"
        "https://monitor.treesir.pub/system/gf6bzpi6976sh3c"
    )
    first = translate(raw)
    assert first != ""
    second = translate(raw)
    assert second == ""  # suppressed by silence window


def test_silence_window_different_metrics_not_suppressed():
    raw_disk = (
        "云悠HK disk usage above threshold\n"
        "Disk usage averaged 94.43% for the previous 1 minute."
    )
    raw_cpu = (
        "云悠HK cpu usage above threshold\n"
        "Cpu usage averaged 88% for the previous 1 minute."
    )
    assert translate(raw_disk) != ""
    assert translate(raw_cpu) != ""  # different metric, not silenced


def test_url_extraction():
    text, url = extract_url("some alert\n\nhttps://example.com/path")
    assert url == "https://example.com/path"
    assert "https://" not in text


def test_no_url():
    text, url = extract_url("some alert without url")
    assert url == ""
    assert text == "some alert without url"


def test_extract_duration_minute():
    assert extract_duration("averaged 94% for the previous 1 minute.") == "已持续 1 分钟"


def test_extract_duration_minutes_plural():
    assert extract_duration("averaged 94% for the previous 5 minutes.") == "已持续 5 分钟"


def test_extract_duration_no_match():
    assert extract_duration("Disk usage averaged 94.43%.") == ""


def test_fallback():
    result = translate("{empty}")
    assert "⚠️ Beszel 通知" in result


def test_memory_alert():
    raw = (
        "七牛香港-主控 memory usage above threshold\n"
        "Memory usage averaged 91.2% for the previous 5 minutes.\n\n"
        "https://monitor.treesir.pub/system/lcfre2r7zvyi3tb"
    )
    result = translate(raw)
    assert "内存使用率" in result
    assert "91.2%" in result
    assert "已持续 5 分钟" in result


def test_legacy_pattern_with_threshold():
    raw = "CPU on 七牛香港-主控 exceeded 85% (current: 92.3%)"
    result = translate(raw)
    assert "🚨 告警" in result
    assert "七牛香港-主控" in result
    assert "92.3%" in result
    assert "85%" in result
