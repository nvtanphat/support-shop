#!/usr/bin/env bash
# Dump the production database to ./backups/<timestamp>.dump (custom format, restorable with ops/restore.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
file="backups/$(date +%Y%m%d_%H%M%S).dump"
docker compose -f docker-compose.prod.yml exec -T postgres   pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-shopagent}" -F c > "$file"
echo "Backup written: $file ($(du -h "$file" | cut -f1))"
# Keep the 14 most recent dumps.
ls -1t backups/*.dump | tail -n +15 | xargs -r rm --
