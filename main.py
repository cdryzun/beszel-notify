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
    "LoadAvg1": "1分钟平均负载",
    "LoadAvg5": "5分钟平均负载",
    "LoadAvg15": "15分钟平均负载",
}

STATUS_ZH: dict[str, str] = {
    "up": "已恢复在线",
    "down": "已离线",
}


def now_cst() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M CST")


def translate(raw: str) -> str:
    ts = now_cst()

    # Pattern A: "Metric on System exceeded N% (current: V%)"
    m = re.search(
        r"(\w+)\s+on\s+(.+?)\s+exceeded\s+([\d.]+)%.*?current:\s*([\d.]+)%",
        raw,
        re.IGNORECASE,
    )
    if m:
        metric, system, threshold, current = m.groups()
        metric_zh = METRIC_ZH.get(metric, metric)
        return (
            f"【告警】{system}\n"
            f"━━━━━━━━━━━━━━\n"
            f"  {metric_zh}  {current}% / {threshold}%\n"
            f"━━━━━━━━━━━━━━\n"
            f"{ts}"
        )

    # Pattern B: "System is down/up"
    m = re.search(r"(.+?)\s+is\s+(down|up)\b", raw, re.IGNORECASE)
    if m:
        system, status = m.groups()
        status_lower = status.lower()
        header = "【节点离线】" if status_lower == "down" else "【节点恢复】"
        status_zh = STATUS_ZH.get(status_lower, status)
        return f"{header}{system}\n{status_zh}\n{ts}"

    # Pattern C: "System status changed to down/up"
    m = re.search(r"(.+?)\s+status\s+changed.*?(down|up)", raw, re.IGNORECASE)
    if m:
        system, status = m.groups()
        status_lower = status.lower()
        header = "【节点离线】" if status_lower == "down" else "【节点恢复】"
        status_zh = STATUS_ZH.get(status_lower, status)
        return f"{header}{system}\n{status_zh}\n{ts}"

    # Pattern D: "Metric exceeded N% on System"
    m = re.search(
        r"(\w+)\s+exceeded\s+([\d.]+)%\s+on\s+(.+?)(?:\s|$)",
        raw,
        re.IGNORECASE,
    )
    if m:
        metric, threshold, system = m.groups()
        metric_zh = METRIC_ZH.get(metric, metric)
        return (
            f"【告警】{system}\n"
            f"━━━━━━━━━━━━━━\n"
            f"  {metric_zh}  超过 {threshold}%\n"
            f"━━━━━━━━━━━━━━\n"
            f"{ts}"
        )

    # Fallback: forward raw message wrapped in Chinese header
    logger.warning("No pattern matched, forwarding raw: %s", raw)
    return f"【Beszel 告警】\n{raw}\n{ts}"


async def send_telegram(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, skip send")
        return
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
        )
        resp.raise_for_status()
        logger.info("Telegram sent, status=%s", resp.status_code)


@app.post("/notify")
async def notify(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}

    logger.info("Incoming payload: %s", body)

    raw = body.get("message") or body.get("text") or str(body)
    zh = translate(raw)
    logger.info("Translated: %s", zh)

    await send_telegram(zh)
    return JSONResponse({"ok": True})


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.post("/test")
async def test() -> JSONResponse:
    sample = "CPU on 测试节点 exceeded 85% (current: 92.3%)"
    zh = translate(sample)
    await send_telegram(zh)
    return JSONResponse({"ok": True, "message": zh})
