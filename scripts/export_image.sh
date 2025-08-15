#!/usr/bin/env bash
set -euo pipefail
IMAGE_NAME=${1:-opuslike}
IMAGE_TAG=${2:-latest}
OUT_TAR=${3:-opuslike_image.tar}
echo "Building $IMAGE_NAME:$IMAGE_TAG ..."
docker build -t "$IMAGE_NAME:$IMAGE_TAG" .
echo "Saving to $OUT_TAR ..."
docker save "$IMAGE_NAME:$IMAGE_TAG" -o "$OUT_TAR"
echo "Done. Load with: docker load -i $OUT_TAR"
