import os
import re
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

METRIC_ZH: dict[str, str] = {
    "CPU": "CPU 使用率",
    "Memory": "内存使用率",
    "Disk": "磁盘使用率",
    "Bandwidth": "网络带宽",
    "Temperature": "温度",
    "Status": "节点状态",
    "GPU": "GPU 使用率",
    "LoadAvg1": "1分钟负载",
    "LoadAvg5": "5分钟负载",
    "LoadAvg15": "15分钟负载",
}

STATUS_ZH: dict[str, str] = {
    "up": "已恢复在线",
    "down": "已离线",
}

METRIC_ICON: dict[str, str] = {
    "CPU": "CPU",
    "Memory": "内存",
    "Disk": "磁盘",
    "Bandwidth": "带宽",
    "Temperature": "温度",
    "GPU": "GPU",
    "LoadAvg1": "负载",
    "LoadAvg5": "负载",
    "LoadAvg15": "负载",
}


def now_cst() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M CST")


async def extract_message(request: Request) -> str:
    """Try every possible location Shoutrrr might put the message."""
    raw_bytes = await request.body()
    raw_str = raw_bytes.decode("utf-8", errors="replace").strip()

    logger.info("Headers: %s", dict(request.headers))
    logger.info("Query params: %s", dict(request.query_params))
    logger.info("Raw body (%d bytes): %r", len(raw_bytes), raw_str[:500])

    # 1. Query parameter
    if request.query_params.get("message"):
        return request.query_params["message"]

    # 2. Plain text body (Shoutrrr default without template)
    if raw_str and not raw_str.startswith("{") and not raw_str.startswith("["):
        return raw_str

    # 3. JSON body
    if raw_str:
        import json
        try:
            body = json.loads(raw_str)
            for key in ("message", "text", "body", "content", "alert"):
                if body.get(key):
                    return str(body[key])
            # Beszel may send structured data directly
            if isinstance(body, dict) and body:
                return str(body)
        except json.JSONDecodeError:
            pass

    # 4. Form-encoded body
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        for key in ("message", "text", "body"):
            if form.get(key):
                return str(form[key])

    return raw_str or "{empty}"


def translate(raw: str) -> str:
    ts = now_cst()

    # Pattern A: "Metric on System exceeded N% (current: V%)"
    m = re.search(
        r"(\w+)\s+on\s+(.+?)\s+exceeded\s+([\d.]+)[%]?.*?current[:\s]+([\d.]+)[%]?",
        raw, re.IGNORECASE,
    )
    if m:
        metric, system, threshold, current = m.groups()
        metric_zh = METRIC_ZH.get(metric, metric)
        return (
            f"告警 | {system}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{metric_zh}：{current}%（阈值 {threshold}%）\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{ts}"
        )

    # Pattern B: "System is down/up"
    m = re.search(r"(.+?)\s+is\s+(down|up)\b", raw, re.IGNORECASE)
    if m:
        system, status = m.groups()
        status_lower = status.lower()
        header = "节点离线" if status_lower == "down" else "节点恢复"
        status_zh = STATUS_ZH.get(status_lower, status)
        return f"{header} | {system}\n{status_zh}\n{ts}"

    # Pattern C: "System status changed to down/up"
    m = re.search(r"(.+?)\s+status.*?(down|up)", raw, re.IGNORECASE)
    if m:
        system, status = m.groups()
        status_lower = status.lower()
        header = "节点离线" if status_lower == "down" else "节点恢复"
        status_zh = STATUS_ZH.get(status_lower, status)
        return f"{header} | {system}\n{status_zh}\n{ts}"

    # Pattern D: "Metric exceeded N% on System"
    m = re.search(
        r"(\w+)\s+exceeded\s+([\d.]+)[%]?\s+on\s+(.+?)(?:\s|$)",
        raw, re.IGNORECASE,
    )
    if m:
        metric, threshold, system = m.groups()
        metric_zh = METRIC_ZH.get(metric, metric)
        return (
            f"告警 | {system}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{metric_zh}：超过阈值 {threshold}%\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{ts}"
        )

    # Fallback
    logger.warning("No pattern matched, raw: %r", raw)
    return f"Beszel 告警\n{raw}\n{ts}"


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
    logger.info("Extracted message: %r", raw)
    zh = translate(raw)
    logger.info("Translated: %s", zh)
    await send_telegram(zh)
    return JSONResponse({"ok": True})


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.post("/test")
async def test() -> JSONResponse:
    sample = "CPU on 七牛香港-主控 exceeded 85% (current: 92.3%)"
    zh = translate(sample)
    await send_telegram(zh)
    return JSONResponse({"ok": True, "message": zh})
