# beszel-notify

A lightweight webhook middleware that receives [Beszel](https://beszel.dev) monitoring alerts and forwards them to Telegram in Chinese.

## Features

- Translates Beszel English alert messages to Chinese
- Supports all Beszel alert types: CPU, memory, disk, bandwidth, temperature, node status
- CST (UTC+8) timestamps on every notification
- Graceful fallback for unrecognized message formats
- `/health` endpoint for container health checks
- `/test` endpoint for quick end-to-end verification

## Quick Start

### 1. Deploy with Docker Compose

```bash
cp .env.example .env
# Edit .env with your Telegram credentials
docker compose up -d
```

### 2. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram Bot API token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Target chat/group ID (negative for groups) |

## Notification Format

### Threshold Alert

```
告警触发 | 七牛香港-主控
指标：CPU 使用率
当前值：92.3%  阈值：85%
时间：2026-06-06 19:00 CST
```

### Node Down

```
节点离线 | 云悠HK
状态：已离线
时间：2026-06-06 19:00 CST
```

### Node Recovered

```
节点恢复 | 云悠HK
状态：已恢复在线
时间：2026-06-06 19:00 CST
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/notify` | Receive Beszel webhook payload |
| `GET` | `/health` | Health check |
| `POST` | `/test` | Send a test message to verify the pipeline |

## Integration with Beszel

### Step 1: Deploy this service

```bash
docker compose up -d
```

### Step 2: Update Beszel notification URL

In the Beszel database, change the webhook URL in `user_settings`:

```bash
# Stop Beszel Hub first (required due to WAL mode)
docker compose stop beszel

# Update webhook URL
python3 << 'EOF'
import sqlite3, json

db = sqlite3.connect('/opt/beszel/data/data.db')
cur = db.cursor()
cur.execute("SELECT id, settings FROM user_settings LIMIT 1")
rid, raw = cur.fetchone()
s = json.loads(raw)
s['webhooks'] = ['generic://beszel-notify:8765/notify?disabletls=yes']
cur.execute("UPDATE user_settings SET settings=? WHERE id=?", (json.dumps(s), rid))
db.commit()
db.close()
EOF

# Restart Beszel Hub
docker compose start beszel
```

### Step 3: Verify

```bash
curl -X POST http://localhost:8765/test
```

You should receive a test message in your Telegram group.

### Shoutrrr URL format

Beszel uses [Shoutrrr](https://github.com/nicholas-fedor/shoutrrr) for webhook delivery.
The generic webhook URL for this service:

```
generic://beszel-notify:8765/notify?disabletls=yes
```

When deployed in the same Docker network as Beszel Hub, use the container name as hostname.
If deployed separately, replace `beszel-notify` with the host IP or domain.

## Development

```bash
pip install -r requirements.txt
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=xxx uvicorn main:app --reload
```

## Docker Image

Pre-built multi-arch images (amd64 / arm64) are available at:

```
ghcr.io/cdryzun/beszel-notify:latest
```
