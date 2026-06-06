# beszel-notify

A lightweight webhook middleware that receives [Beszel](https://beszel.dev) monitoring alerts and forwards them to Telegram in Chinese.

## Features

- Translates Beszel English alert messages to Chinese
- Distinguishes alert types with emoji: 🚨 告警 / ✅ 恢复 / 🔴 节点离线 / ⚠️ 其他
- Extracts duration from alert ("已持续 N 分钟")
- Preserves the system detail URL in every notification
- 5-minute silence window per system+metric to suppress repeated alerts
- Recovery notifications bypass the silence window and are always delivered
- Recovery clears the silence window so the next alert fires normally
- `/health` endpoint for container health checks
- `/test` endpoint for end-to-end verification

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
| `SILENCE_WINDOW_SEC` | No | Seconds between repeated alerts per metric (default: 300) |

## Notification Format

### Threshold Alert (above threshold)

```
🚨 告警 | 七牛香港-主控
━━━━━━━━━━━━━━━━━
指标：CPU 使用率
当前：92.3%（超过阈值）
持续：已持续 5 分钟
━━━━━━━━━━━━━━━━━
时间：2026-06-06 19:00 CST
详情：https://monitor.treesir.pub/system/lcfre2r7zvyi3tb
```

### Recovery (below threshold)

```
✅ 恢复 | 七牛香港-主控
━━━━━━━━━━━━━━━━━
指标：CPU 使用率
当前：71.3%（低于阈值）
持续：已持续 1 分钟
━━━━━━━━━━━━━━━━━
时间：2026-06-06 19:10 CST
详情：https://monitor.treesir.pub/system/lcfre2r7zvyi3tb
```

### Node Down / Up

```
🔴 节点离线 | 云悠HK
━━━━━━━━━━━━━━━━━
状态：已离线
━━━━━━━━━━━━━━━━━
时间：2026-06-06 19:00 CST
详情：https://monitor.treesir.pub/system/gf6bzpi6976sh3c
```

```
✅ 节点恢复 | 云悠HK
━━━━━━━━━━━━━━━━━
状态：已恢复在线
━━━━━━━━━━━━━━━━━
时间：2026-06-06 19:05 CST
详情：https://monitor.treesir.pub/system/gf6bzpi6976sh3c
```

## Silence Window Behavior

| Event | Behavior |
|-------|----------|
| First alert | Delivered, silence window starts |
| Same alert within window | Suppressed |
| Recovery notification | Always delivered, clears silence window |
| Alert after recovery | Delivered normally |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/notify` | Receive Beszel webhook payload (plain text or JSON) |
| `GET` | `/health` | Health check |
| `POST` | `/test` | Send a test alert to verify the pipeline |

## Integration with Beszel

### Step 1: Deploy this service

```bash
docker compose up -d
```

### Step 2: Create a shared Docker network

So the Beszel Hub container can reach beszel-notify by hostname:

```bash
docker network create beszel-shared
docker network connect beszel-shared beszel
docker network connect beszel-shared beszel-notify
```

Then add the network to both compose files so it persists across recreates:

```yaml
# In both docker-compose.yml files
networks:
  beszel-shared:
    external: true
```

### Step 3: Configure Beszel webhook URL

Stop Hub, update the webhook URL in the database, restart:

```bash
docker stop beszel
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
docker start beszel
```

### Step 4: Verify

```bash
curl -X POST http://localhost:8765/test
```

You should receive a test alert in your Telegram group.

### Shoutrrr URL format

```
generic://beszel-notify:8765/notify?disabletls=yes
```

The middleware accepts Beszel's plain-text webhook payload directly (no `template=json` needed).

## Important: SQLite WAL Mode

Beszel's SQLite runs in WAL mode. **Always stop the Hub container before modifying the database directly**, otherwise changes will be overwritten by the WAL file.

```bash
# Correct order
docker stop beszel
sqlite3 /opt/beszel/data/data.db "..."
docker start beszel
```

## Development

```bash
pip install -r requirements.txt
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=xxx uvicorn main:app --reload
```

Run tests:

```bash
pytest test_main.py -v
```

## Docker Image

Pre-built multi-arch images (amd64 / arm64) are available at:

```
ghcr.io/cdryzun/beszel-notify:latest
```
