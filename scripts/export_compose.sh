#!/usr/bin/env bash
set -euo pipefail
ARCHIVE=${1:-opuslike_compose_bundle.tar.gz}
echo "Creating compose bundle ($ARCHIVE) ..."
tar czf "$ARCHIVE" docker-compose.yml .env.example
echo "Done."
