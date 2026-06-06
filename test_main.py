from main import translate, extract_url


def test_real_beszel_disk_alert():
    raw = (
        "云悠HK disk usage above threshold\n"
        "Disk usage averaged 94.43% for the previous 1 minute.\n\n"
        "https://monitor.treesir.pub/system/gf6bzpi6976sh3c"
    )
    result = translate(raw)
    assert "云悠HK" in result
    assert "磁盘使用率" in result
    assert "94.43%" in result
    assert "超过" in result
    assert "https://monitor.treesir.pub/system/gf6bzpi6976sh3c" in result


def test_real_beszel_cpu_alert():
    raw = (
        "七牛香港-主控 cpu usage above threshold\n"
        "Cpu usage averaged 87.5% for the previous 5 minutes.\n\n"
        "https://monitor.treesir.pub/system/lcfre2r7zvyi3tb"
    )
    result = translate(raw)
    assert "七牛香港-主控" in result
    assert "CPU 使用率" in result
    assert "87.5%" in result
    assert "https://monitor.treesir.pub/system/lcfre2r7zvyi3tb" in result


def test_node_down():
    raw = "云悠HK is down\n\nhttps://monitor.treesir.pub/system/gf6bzpi6976sh3c"
    result = translate(raw)
    assert "离线" in result
    assert "云悠HK" in result
    assert "https://monitor.treesir.pub" in result


def test_node_up():
    raw = "云悠HK is up\n\nhttps://monitor.treesir.pub/system/gf6bzpi6976sh3c"
    result = translate(raw)
    assert "恢复" in result


def test_url_extraction():
    text, url = extract_url("some alert\n\nhttps://example.com/path")
    assert url == "https://example.com/path"
    assert "https://" not in text


def test_no_url():
    text, url = extract_url("some alert without url")
    assert url == ""
    assert text == "some alert without url"


def test_fallback():
    result = translate("{empty}")
    assert "Beszel 告警" in result


def test_memory_alert():
    raw = (
        "七牛香港-主控 memory usage above threshold\n"
        "Memory usage averaged 91.2% for the previous 5 minutes.\n\n"
        "https://monitor.treesir.pub/system/lcfre2r7zvyi3tb"
    )
    result = translate(raw)
    assert "内存使用率" in result
    assert "91.2%" in result
