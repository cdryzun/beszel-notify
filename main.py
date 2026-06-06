import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="beszel-notify", version="1.0.0")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CST = timezone(timedelta(hours=8))

# Beszel metric name → Chinese
METRIC_ZH: dict[str, str] = {
    "cpu": "CPU 使用率",
    "memory": "内存使用率",
    "disk": "磁盘使用率",
    "bandwidth": "网络带宽",
    "temperature": "温度",
    "status": "节点状态",
    "gpu": "GPU 使用率",
    "loadavg1": "1分钟负载",
    "loadavg5": "5分钟负载",
    "loadavg15": "15分钟负载",
}

STATUS_ZH: dict[str, str] = {
    "up": "已恢复在线",
    "down": "已离线",
}


def now_cst() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M CST")


def extract_url(text: str) -> tuple[str, str]:
    """Pull the https://... link out of the message, return (text_without_url, url)."""
    url_pattern = r"(https?://\S+)"
    m = re.search(url_pattern, text)
    if m:
        url = m.group(1).rstrip(".")
        cleaned = re.sub(url_pattern, "", text).strip()
        return cleaned, url
    return text, ""


def translate(raw: str) -> str:
    ts = now_cst()
    text, url = extract_url(raw)
    url_line = f"\n{url}" if url else ""

    # ── Beszel real format ──────────────────────────────────────────
    # Line 1: "{system} {metric} above/below threshold"
    # Line 2: "{Metric} usage averaged {value}% for the previous N minute(s)."
    # ───────────────────────────────────────────────────────────────

    # Pattern A: threshold alert (above/below)
    m = re.search(
        r"^(.+?)\s+([\w]+)\s+(?:usage\s+)?(?:above|below)\s+threshold",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if m:
        system = m.group(1).strip()
        metric_key = m.group(2).lower()
        metric_zh = METRIC_ZH.get(metric_key, m.group(2))

        # Extract current value from line 2
        val_m = re.search(r"averaged?\s+([\d.]+)%", text, re.IGNORECASE)
        value_str = f"{val_m.group(1)}%" if val_m else ""

        direction = "超过" if "above" in text.lower() else "低于"

        value_part = f"{metric_zh}：{value_str}（{direction}阈值）" if value_str else f"{metric_zh}：{direction}阈值"

        return (
            f"告警 | {system}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{value_part}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{ts}{url_line}"
        )

    # Pattern B: status down/up  "System is down/up"
    m = re.search(r"^(.+?)\s+is\s+(down|up)\b", text, re.IGNORECASE | re.MULTILINE)
    if m:
        system, status = m.group(1).strip(), m.group(2).lower()
        header = "节点离线" if status == "down" else "节点恢复"
        return f"{header} | {system}\n{STATUS_ZH.get(status, status)}\n{ts}{url_line}"

    # Pattern C: legacy "Metric on System exceeded N% (current: V%)"
    m = re.search(
        r"(\w+)\s+on\s+(.+?)\s+exceeded\s+([\d.]+)%.*?current[:\s]+([\d.]+)%",
        text, re.IGNORECASE,
    )
    if m:
        metric_key, system, threshold, current = m.groups()
        metric_zh = METRIC_ZH.get(metric_key.lower(), metric_key)
        return (
            f"告警 | {system}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{metric_zh}：{current}%（阈值 {threshold}%）\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{ts}{url_line}"
        )

    # Fallback
    logger.warning("No pattern matched, raw: %r", raw)
    return f"Beszel 告警\n{text}\n{ts}{url_line}"


async def extract_message(request: Request) -> str:
    """Read body as plain text first (Shoutrrr default), fallback to JSON."""
    raw_bytes = await request.body()
    raw_str = raw_bytes.decode("utf-8", errors="replace").strip()

    logger.info("Content-Type: %s", request.headers.get("content-type", ""))
    logger.info("Raw body: %r", raw_str[:500])

    if not raw_str:
        return "{empty}"

    # Plain text (Shoutrrr default — not JSON)
    if not raw_str.startswith("{") and not raw_str.startswith("["):
        return raw_str

    # JSON body
    try:
        body = json.loads(raw_str)
        for key in ("message", "text", "body", "content"):
            if body.get(key):
                return str(body[key])
    except json.JSONDecodeError:
        pass

    return raw_str


async def send_telegram(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("Telegram not configured, skip")
        return
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
        )
        resp.raise_for_status()
        logger.info("Telegram sent %s", resp.status_code)


@app.post("/notify")
async def notify(request: Request) -> JSONResponse:
    raw = await extract_message(request)
    logger.info("Extracted: %r", raw)
    zh = translate(raw)
    logger.info("Translated:\n%s", zh)
    await send_telegram(zh)
    return JSONResponse({"ok": True})


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.post("/test")
async def test() -> JSONResponse:
    # Simulate exact Beszel real payload
    sample = (
        "云悠HK disk usage above threshold\n"
        "Disk usage averaged 94.43% for the previous 1 minute.\n\n"
        "https://monitor.treesir.pub/system/gf6bzpi6976sh3c"
    )
    zh = translate(sample)
    await send_telegram(zh)
    return JSONResponse({"ok": True, "message": zh})
