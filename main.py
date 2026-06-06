import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict

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
# Minimum seconds between repeated alerts for the same system+metric
SILENCE_WINDOW = int(os.environ.get("SILENCE_WINDOW_SEC", "300"))
CST = timezone(timedelta(hours=8))

SEPARATOR = "━━━━━━━━━━━━━━━━━"

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

DURATION_UNIT_ZH: dict[str, str] = {
    "second": "秒",
    "minute": "分钟",
    "hour": "小时",
    "day": "天",
}

EVENT_EMOJI: dict[str, str] = {
    "alert": "🚨",
    "down": "🔴",
    "up": "✅",
    "fallback": "⚠️",
}

# In-memory silence window: (system, metric) → last notified timestamp
_last_sent: dict[tuple[str, str], datetime] = defaultdict(lambda: datetime.min)


def now_cst() -> datetime:
    return datetime.now(CST)


def now_cst_str() -> str:
    return now_cst().strftime("%Y-%m-%d %H:%M CST")


def is_silenced(system: str, metric: str) -> bool:
    key = (system, metric)
    elapsed = (now_cst().replace(tzinfo=None) - _last_sent[key]).total_seconds()
    return elapsed < SILENCE_WINDOW


def mark_sent(system: str, metric: str) -> None:
    _last_sent[(system, metric)] = now_cst().replace(tzinfo=None)


def extract_url(text: str) -> tuple[str, str]:
    m = re.search(r"(https?://\S+)", text)
    if m:
        url = m.group(1).rstrip(".")
        cleaned = re.sub(r"https?://\S+", "", text).strip()
        return cleaned, url
    return text, ""


def extract_duration(text: str) -> str:
    m = re.search(
        r"for the previous\s+([\d.]+)\s+(second|minute|hour|day)s?\b",
        text, re.IGNORECASE,
    )
    if not m:
        return ""
    value = m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1)
    unit = DURATION_UNIT_ZH.get(m.group(2).lower(), m.group(2).lower())
    return f"已持续 {value} {unit}"


def format_url_line(url: str) -> str:
    return f"\n详情：{url}" if url else ""


def translate(raw: str) -> str:
    ts = now_cst_str()
    text, url = extract_url(raw)
    url_line = format_url_line(url)

    # ── Pattern A: Beszel threshold alert ──────────────────────────
    # "{system} {metric} [usage] above/below threshold"
    # "{Metric} usage averaged {value}% for the previous N minute(s)."
    m = re.search(
        r"^(.+?)\s+([\w]+)\s+(?:usage\s+)?(above|below)\s+threshold",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if m:
        system = m.group(1).strip()
        metric_key = m.group(2).lower()
        direction_word = m.group(3).lower()
        metric_zh = METRIC_ZH.get(metric_key, m.group(2))
        direction = "超过" if direction_word == "above" else "低于"

        val_m = re.search(r"averaged?\s+([\d.]+)%", text, re.IGNORECASE)
        value_str = f"{val_m.group(1)}%" if val_m else ""
        duration = extract_duration(text)

        current_line = (
            f"当前：{value_str}（{direction}阈值）" if value_str else f"当前：{direction}阈值"
        )
        duration_line = f"\n持续：{duration}" if duration else ""

        if is_silenced(system, metric_key):
            logger.info("Silenced alert for %s/%s within %ds window", system, metric_key, SILENCE_WINDOW)
            return ""

        mark_sent(system, metric_key)
        return (
            f"{EVENT_EMOJI['alert']} 告警 | {system}\n"
            f"{SEPARATOR}\n"
            f"指标：{metric_zh}\n"
            f"{current_line}{duration_line}\n"
            f"{SEPARATOR}\n"
            f"时间：{ts}{url_line}"
        )

    # ── Pattern B: node status down / up ───────────────────────────
    m = re.search(r"^(.+?)\s+is\s+(down|up)\b", text, re.IGNORECASE | re.MULTILINE)
    if m:
        system, status = m.group(1).strip(), m.group(2).lower()
        header = "节点离线" if status == "down" else "节点恢复"
        mark_sent(system, "status")
        return (
            f"{EVENT_EMOJI[status]} {header} | {system}\n"
            f"{SEPARATOR}\n"
            f"状态：{STATUS_ZH.get(status, status)}\n"
            f"{SEPARATOR}\n"
            f"时间：{ts}{url_line}"
        )

    # ── Pattern C: legacy "Metric on System exceeded N% (current: V%)" ─
    m = re.search(
        r"(\w+)\s+on\s+(.+?)\s+exceeded\s+([\d.]+)%.*?current[:\s]+([\d.]+)%",
        text, re.IGNORECASE,
    )
    if m:
        metric_key, system, threshold, current = m.groups()
        metric_zh = METRIC_ZH.get(metric_key.lower(), metric_key)

        if is_silenced(system, metric_key.lower()):
            return ""

        mark_sent(system, metric_key.lower())
        return (
            f"{EVENT_EMOJI['alert']} 告警 | {system}\n"
            f"{SEPARATOR}\n"
            f"指标：{metric_zh}\n"
            f"当前：{current}%（阈值 {threshold}%）\n"
            f"{SEPARATOR}\n"
            f"时间：{ts}{url_line}"
        )

    # ── Fallback ────────────────────────────────────────────────────
    logger.warning("No pattern matched, raw: %r", raw)
    return f"{EVENT_EMOJI['fallback']} Beszel 通知\n{text}\n时间：{ts}{url_line}"


async def send_telegram(text: str) -> None:
    if not text:
        return
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


async def extract_message(request: Request) -> str:
    raw_bytes = await request.body()
    raw_str = raw_bytes.decode("utf-8", errors="replace").strip()

    logger.info("Content-Type: %s", request.headers.get("content-type", ""))
    logger.info("Raw body: %r", raw_str[:500])

    if not raw_str:
        return "{empty}"

    # Plain text — Shoutrrr default (no template param)
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


@app.post("/notify")
async def notify(request: Request) -> JSONResponse:
    raw = await extract_message(request)
    logger.info("Extracted: %r", raw)
    zh = translate(raw)
    if zh:
        logger.info("Translated:\n%s", zh)
        await send_telegram(zh)
    return JSONResponse({"ok": True})


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.post("/test")
async def test() -> JSONResponse:
    sample = (
        "云悠HK disk usage above threshold\n"
        "Disk usage averaged 94.43% for the previous 1 minute.\n\n"
        "https://monitor.treesir.pub/system/gf6bzpi6976sh3c"
    )
    # bypass silence window for test
    _last_sent.clear()
    zh = translate(sample)
    await send_telegram(zh)
    return JSONResponse({"ok": True, "message": zh})
