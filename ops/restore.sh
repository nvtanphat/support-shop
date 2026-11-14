#!/usr/bin/env bash
# Restore a dump into a scratch database and run the data invariants against it. Never touches the live database.
# Usage: ops/restore.sh backups/<file>.dump
set -euo pipefail
cd "$(dirname "$0")/.."
dump="${1:?usage: ops/restore.sh <dump file>}"
user="${POSTGRES_USER:-postgres}"
compose="docker compose -f docker-compose.prod.yml"
$compose exec -T postgres psql -U "$user" -c "DROP DATABASE IF EXISTS shopagent_restore;"
$compose exec -T postgres psql -U "$user" -c "CREATE DATABASE shopagent_restore;"
$compose exec -T postgres pg_restore -U "$user" -d shopagent_restore --no-owner < "$dump"
$compose run --rm   -e DATABASE_URL="postgresql+asyncpg://$user:${POSTGRES_PASSWORD}@postgres:5432/shopagent_restore"   api python -m shopagent.cli verify-data
echo "Restore drill passed for $dump"
