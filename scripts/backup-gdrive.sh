#!/bin/bash
# Daily mem0 backup to Google Drive
# Usage: ./backup-gdrive.sh
# Cron:  0 23 * * * /home/YOUR_USER/.local/bin/mem0-backup-gdrive.sh
set -e

HOME_DIR="${HOME:-/home/$(whoami)}"
BACKUP_FILE="/tmp/mem0-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
LOG="/tmp/mem0-backup.log"

echo "[$(date)] Starting backup..." >> "$LOG"

tar czf "$BACKUP_FILE" \
  -C / \
  "${HOME_DIR#/}/.copilot/mem0/memories.sqlite" \
  "${HOME_DIR#/}/.copilot/session-store.db" \
  "${HOME_DIR#/}/.copilot/mcp-config.json" \
  "${HOME_DIR#/}/data/config.json" \
  "${HOME_DIR#/}/.local/bin/mem0-gateway" \
  "${HOME_DIR#/}/.config/systemd/user/ollama.service" \
  "${HOME_DIR#/}/.config/systemd/user/mem0-supergateway.service" \
  2>/dev/null

rclone copy "$BACKUP_FILE" gdrive:mem0-backups/ 2>> "$LOG"
rm -f "$BACKUP_FILE"

# Keep only last 30 backups
rclone delete gdrive:mem0-backups/ --min-age 30d 2>> "$LOG"

echo "[$(date)] Backup complete" >> "$LOG"
