#!/bin/bash
# Backup PostgreSQL — run daily via cron on your VPS
# Example cron: 0 2 * * * /path/to/cryptoagent/scripts/backup-db.sh

set -e
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILE="$BACKUP_DIR/cryptoagent_${TIMESTAMP}.sql.gz"

docker compose exec -T db pg_dump -U "${POSTGRES_USER:-cryptoagent}" "${POSTGRES_DB:-cryptoagent}" | gzip > "$FILE"

# Keep last 14 daily backups
ls -t "$BACKUP_DIR"/cryptoagent_*.sql.gz | tail -n +15 | xargs -r rm --

echo "Backup saved: $FILE"
