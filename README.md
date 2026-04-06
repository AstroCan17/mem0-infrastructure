# mem0 Infrastructure Manual

> **Last updated:** 2026-04-06
> **System:** Kali Linux Rolling 2026.1 • Node.js v22 • Python 3.13

This manual covers fresh installation, daily operations, and backup/restore for the
mem0 + Supergateway stack used by Copilot/Cursor agents. Bifrost was removed
to simplify the deployment (no Docker dependency, local-only HTTP bridge).

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Fresh Install (from scratch)](#2-fresh-install)
3. [Start / Stop / Health Check](#3-start--stop--health-check)
4. [Backup & Restore](#4-backup--restore)
5. [Troubleshooting](#5-troubleshooting)
6. [File Reference](#6-file-reference)

---

## 1. Architecture Overview

```
┌─────────────────────┐
│  Agent CLIs          │
│  (Copilot / Cursor)  │
└───────────┬─────────┘
            │ stdio (default) or HTTP (port 8765)
            ▼
      ┌──────────────┐
      │ Supergateway │  (Node.js bridge)
      │ stdio→HTTP   │
      └──────┬───────┘
             │ stdio
             ▼
      ┌──────────────┐
      │  mem0-mcp    │  (MCP server)
      └──────┬───────┘
             │
 ┌───────────┴───────────┐
 ▼                       ▼
┌─────────────┐      ┌──────────────┐
│ SQLite      │      │ Ollama       │
│ memories.db │      │ (embeddings) │
└─────────────┘      └──────────────┘
```

**Access paths:**
- **Direct (stdio, recommended):** Copilot/Cursor CLI → mem0-mcp → SQLite + Ollama
- **HTTP (optional):** Any HTTP client → Supergateway:8765 → mem0-mcp → SQLite + Ollama

---

## 2. Fresh Install

### 2.1 Prerequisites

```bash
# Node.js 22+ and npm
sudo apt update && sudo apt install -y nodejs npm

# Utilities
sudo apt install -y curl sqlite3
```

### 2.2 Ollama

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Verify
ollama --version
# Expected: ollama version is 0.20.0 (or newer)
```

**Create systemd user service:**

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/ollama.service << 'EOF'
[Unit]
Description=Ollama Local LLM Server
After=network.target

[Service]
Type=simple
ExecStart=%h/.local/bin/ollama serve
Restart=on-failure
RestartSec=3
Environment=HOME=%h
Environment=OLLAMA_HOST=127.0.0.1:11434
Environment=OLLAMA_KEEP_ALIVE=-1

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user start ollama
```

> **Note:** `OLLAMA_KEEP_ALIVE=-1` keeps models loaded permanently in memory.
> If Ollama was installed to a different path, update `ExecStart` accordingly.
>
> **Important:** Binding to `127.0.0.1` keeps Ollama local-only (safer). If you
> ever need remote/container access, change `OLLAMA_HOST` to `0.0.0.0:11434`
> and add your own firewalling.

**Pull the embedding model:**

```bash
ollama pull mxbai-embed-large
# Size: ~670 MB, 1024 dimensions, <1s inference on CPU
```

**Verify:**

```bash
curl -s http://127.0.0.1:11434/api/embed \
  -d '{"model":"mxbai-embed-large","input":"test"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OK - {len(d[\"embeddings\"][0])} dims')"
# Expected: OK - 1024 dims
```

### 2.3 mem0-mcp

```bash
sudo npm install -g mem0-mcp
# Installs to: /usr/local/lib/node_modules/mem0-mcp/
# Binary at:   /usr/local/bin/mem0-mcp

# Verify
which mem0-mcp
# Expected: /usr/local/bin/mem0-mcp
```

**Create data directory:**

```bash
mkdir -p ~/.copilot/mem0
```

### 2.4 Supergateway

```bash
sudo npm install -g supergateway
# Binary at: /usr/local/bin/supergateway

# Verify
supergateway --help | head -1
```

**Create the mem0 gateway wrapper script:**

```bash
mkdir -p ~/.local/bin

cat > ~/.local/bin/mem0-gateway << 'WRAPPER'
#!/bin/sh
export HOME="$HOME"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export MEM0_STORE_PATH="$HOME/.copilot/mem0"
export MEM0_EMBED_MODEL=mxbai-embed-large
export MEM0_OLLAMA_TIMEOUT_MS=60000
exec /usr/local/bin/mem0-mcp
WRAPPER

chmod +x ~/.local/bin/mem0-gateway
```

> Template copy available at `configs/mem0-gateway.sh`.

> **Key env vars:**
> - `MEM0_EMBED_MODEL` — Ollama model for embeddings (default: qwen3-embedding:latest)
> - `MEM0_OLLAMA_TIMEOUT_MS` — Timeout for Ollama API calls (default: 10000, we use 60000)
> - `MEM0_STORE_PATH` — Directory for SQLite database

**Create systemd user service for Supergateway:**

```bash
cat > ~/.config/systemd/user/mem0-supergateway.service << 'EOF'
[Unit]
Description=mem0-mcp Supergateway (streamableHttp)
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
ExecStart=/usr/local/bin/supergateway \
  --stdio %h/.local/bin/mem0-gateway \
  --outputTransport streamableHttp \
  --port 8765 \
  --streamableHttpPath /mcp \
  --healthEndpoint /healthz \
  --logLevel info
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable mem0-supergateway
```

> **Important:** Enable linger so user services survive logout:
> ```bash
> sudo loginctl enable-linger $USER
> ```

### 2.5 Copilot CLI MCP Configuration

```bash
cat > ~/.copilot/mcp-config.json << MCP_CONFIG
{
  "mcpServers": {
    "mem0": {
      "tools": ["*"],
      "command": "/usr/local/bin/mem0-mcp",
      "args": [],
      "env": {
        "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
        "MEM0_STORE_PATH": "$HOME/.copilot/mem0",
        "MEM0_EMBED_MODEL": "mxbai-embed-large",
        "MEM0_OLLAMA_TIMEOUT_MS": "60000"
      }
    }
  }
}
MCP_CONFIG
```

### 2.6 Verification

Run these after all components are started:

```bash
# 1. Ollama
curl -s http://127.0.0.1:11434/api/tags | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(f'✓ Ollama: {len(d[\"models\"])} models')"

# 2. Supergateway
curl -s http://127.0.0.1:8765/healthz | grep -q "ok" && echo "✓ Supergateway: healthy" || echo "✗ Supergateway: down"

# 3. mem0 health via Supergateway
curl -s -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"mem0-health","arguments":{}}}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['content'][0]['text'][:100])"
```

---

## 3. Start / Stop / Health Check

### 3.1 Start All Services

Run in this order:

```bash
# 1. Ollama
systemctl --user start ollama
sleep 2

# 2. Supergateway (mem0-mcp bridge)
systemctl --user start mem0-supergateway
sleep 3
```

### 3.2 Stop All Services

```bash
systemctl --user stop mem0-supergateway
systemctl --user stop ollama
```

### 3.3 Service Status

```bash
systemctl --user status ollama mem0-supergateway --no-pager
```

### 3.4 Health Check (one-liner)

```bash
echo "Ollama:"; curl -sf http://127.0.0.1:11434/api/tags > /dev/null && echo "  ✓" || echo "  ✗"; \
echo "Supergateway:"; curl -sf http://127.0.0.1:8765/healthz > /dev/null && echo "  ✓" || echo "  ✗"; \
echo "mem0-health:"; curl -sf -X POST http://127.0.0.1:8765/mcp -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"mem0-health","arguments":{}}}' > /dev/null && echo "  ✓" || echo "  ✗"
```

---

## 4. Backup & Restore

### 4.1 Critical Files

| File | Content | Priority |
|------|---------|----------|
| `~/.copilot/mem0/memories.sqlite` | All mem0 memories + embeddings | **Critical** |
| `~/.copilot/session-store.db` | Copilot CLI conversation history | **Critical** |
| `~/.copilot/mcp-config.json` | MCP server definitions | **High** |
| `~/.local/bin/mem0-gateway` | Supergateway wrapper script | **High** |
| `~/.config/systemd/user/ollama.service` | Ollama systemd service | **Medium** |
| `~/.config/systemd/user/mem0-supergateway.service` | Supergateway systemd service | **Medium** |

### 4.2 Manual Backup (tar.gz)

```bash
# Create timestamped backup
BACKUP_FILE="/tmp/mem0-backup-$(date +%Y%m%d-%H%M%S).tar.gz"

tar czf "$BACKUP_FILE" \
  -C / \
  "${HOME#/}/.copilot/mem0/memories.sqlite" \
  "${HOME#/}/.copilot/session-store.db" \
  "${HOME#/}/.copilot/mcp-config.json" \
  "${HOME#/}/.local/bin/mem0-gateway" \
  "${HOME#/}/.config/systemd/user/ollama.service" \
  "${HOME#/}/.config/systemd/user/mem0-supergateway.service" \
  2>/dev/null

echo "Backup created: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
```

### 4.3 Restore from Backup

```bash
# Extract to root (preserves paths)
tar xzf /path/to/mem0-backup-XXXXXXXX-XXXXXX.tar.gz -C /

# Then re-install software (Section 2) and start services (Section 3)
```

### 4.4 Google Drive Backup with rclone

**One-time setup:**

```bash
# Install rclone
sudo apt install -y rclone

# Configure Google Drive remote
rclone config
# Follow the interactive wizard:
#   n) New remote
#   name> gdrive
#   Storage> drive (Google Drive)
#   client_id> (leave blank for default)
#   client_secret> (leave blank)
#   scope> 1 (Full access)
#   root_folder_id> (leave blank)
#   service_account_file> (leave blank)
#   Edit advanced config> n
#   Auto config> y (opens browser for OAuth)
#   Configure as team drive> n
```

**Manual backup to Google Drive:**

```bash
# Create local backup first
BACKUP_FILE="/tmp/mem0-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
tar czf "$BACKUP_FILE" \
  -C / \
  "${HOME#/}/.copilot/mem0/memories.sqlite" \
  "${HOME#/}/.copilot/session-store.db" \
  "${HOME#/}/.copilot/mcp-config.json" \
  "${HOME#/}/data/config.json" \
  "${HOME#/}/.local/bin/mem0-gateway" \
  "${HOME#/}/.config/systemd/user/ollama.service" \
  "${HOME#/}/.config/systemd/user/mem0-supergateway.service" \
  2>/dev/null

# Upload to Google Drive
rclone copy "$BACKUP_FILE" gdrive:mem0-backups/
echo "Uploaded to Google Drive: mem0-backups/$(basename $BACKUP_FILE)"

# Clean local temp
rm -f "$BACKUP_FILE"
```

**Restore from Google Drive:**

```bash
# List available backups
rclone ls gdrive:mem0-backups/

# Download latest
rclone copy gdrive:mem0-backups/ /tmp/mem0-restore/ --include "*.tar.gz"

# Pick the file and extract
LATEST=$(ls -t /tmp/mem0-restore/*.tar.gz | head -1)
tar xzf "$LATEST" -C /
echo "Restored from: $LATEST"
```

### 4.5 Automated Daily Backup (cron)

**Create the backup script:**

```bash
cat > ~/.local/bin/mem0-backup-gdrive.sh << 'SCRIPT'
#!/bin/bash
# Daily mem0 backup to Google Drive
set -e

BACKUP_FILE="/tmp/mem0-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
LOG="/tmp/mem0-backup.log"

echo "[$(date)] Starting backup..." >> "$LOG"

tar czf "$BACKUP_FILE" \
  -C / \
  "${HOME#/}/.copilot/mem0/memories.sqlite" \
  "${HOME#/}/.copilot/session-store.db" \
  "${HOME#/}/.copilot/mcp-config.json" \
  "${HOME#/}/data/config.json" \
  "${HOME#/}/.local/bin/mem0-gateway" \
  "${HOME#/}/.config/systemd/user/ollama.service" \
  "${HOME#/}/.config/systemd/user/mem0-supergateway.service" \
  2>/dev/null

rclone copy "$BACKUP_FILE" gdrive:mem0-backups/ 2>> "$LOG"

rm -f "$BACKUP_FILE"

# Keep only last 30 backups on Google Drive
rclone delete gdrive:mem0-backups/ --min-age 30d 2>> "$LOG"

echo "[$(date)] Backup complete" >> "$LOG"
SCRIPT

chmod +x ~/.local/bin/mem0-backup-gdrive.sh
```

**Add cron job (daily at 23:00):**

```bash
(crontab -l 2>/dev/null; echo "0 23 * * * $HOME/.local/bin/mem0-backup-gdrive.sh") | crontab -
```

**Verify cron:**

```bash
crontab -l | grep mem0
# Expected: 0 23 * * * $HOME/.local/bin/mem0-backup-gdrive.sh
```

---

## 5. Troubleshooting

### Supergateway crashes with "Already connected to a transport"
- **Cause:** SSE mode only supports 1 client. Two clients = crash.
- **Fix:** Always use `--outputTransport streamableHttp` (not SSE).

### mem0 "Timed out after 10000ms contacting Ollama"
- **Cause:** Default timeout too short, especially on cold start.
- **Fix:** Set `MEM0_OLLAMA_TIMEOUT_MS=60000` in wrapper script and mcp-config.json.

### Ollama high CPU usage
- **Cause:** No GPU acceleration; large model loaded in RAM.
- **Fix:** Use smaller embedding model (mxbai-embed-large at 670MB vs qwen3-embedding at 4.7GB). Hardware: RX 460 (4GB VRAM) / Vega (2GB VRAM) are too small for large models + no ROCm installed.

### `mem0-health` reports `modelAvailable: false` despite working system
- **Cause:** Known false negative in the mem0-mcp health check implementation. The internal model availability probe may fail even when Ollama is running and embeddings work correctly.
- **Diagnosis:** If semantic search (`mem0-memory_search`) returns results with scores, the system is healthy regardless of what `mem0-health` reports.
- **Workaround:** Use the end-to-end verification commands in Section 2.6 instead of relying on `mem0-health` alone.

---

## 6. File Reference

### Config Files

| Path | Purpose |
|------|---------|
| `~/.copilot/mcp-config.json` | Copilot CLI MCP server definitions |
| `~/.local/bin/mem0-gateway` | Supergateway wrapper with env vars |
| `~/.config/systemd/user/ollama.service` | Ollama systemd user service |
| `~/.config/systemd/user/mem0-supergateway.service` | Supergateway systemd user service |

### Data Files

| Path | Purpose |
|------|---------|
| `~/.copilot/mem0/memories.sqlite` | mem0 memory storage (embeddings + content) |
| `~/.copilot/session-store.db` | Copilot CLI session/conversation history |

### Ports

| Port | Service | Protocol |
|------|---------|----------|
| 11434 | Ollama | HTTP |
| 8765 | Supergateway | streamableHttp |
