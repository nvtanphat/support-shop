#!/usr/bin/env bash
# Deploy a tagged image: back up, migrate, restart. The previous tag is recorded so ops/rollback.sh can return to it.
# Usage: ops/deploy.sh <image tag>
set -euo pipefail
cd "$(dirname "$0")/.."
tag="${1:?usage: ops/deploy.sh <image tag>}"
compose="docker compose -f docker-compose.prod.yml"

./ops/backup.sh
[ -f .deployed_tag ] && cp .deployed_tag .previous_tag
export IMAGE_TAG="$tag"
$compose pull api worker
$compose run --rm api alembic upgrade head
$compose up -d api worker caddy
echo "$tag" > .deployed_tag

for _ in $(seq 1 30); do
  if curl -fsS http://localhost/readyz > /dev/null; then echo "Deployed $tag"; exit 0; fi
  sleep 2
done
echo "Service did not become ready; run ops/rollback.sh" >&2
exit 1
