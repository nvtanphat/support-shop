#!/usr/bin/env bash
# Return api and worker to the tag recorded before the last deploy. Database migrations are not reverted;
# restore from a backup (ops/restore.sh) if the last release changed the schema incompatibly.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .previous_tag ] || { echo "No previous tag recorded" >&2; exit 1; }
tag="$(cat .previous_tag)"
export IMAGE_TAG="$tag"
docker compose -f docker-compose.prod.yml up -d api worker
echo "$tag" > .deployed_tag
echo "Rolled back to $tag"
