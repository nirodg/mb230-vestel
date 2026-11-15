#!/usr/bin/env bash
set -euo pipefail

# Build hello-world/hello for MB230 (ARMv7 hard-float, static) using Docker.
# Uses ubuntu:16.04 toolchain for broad glibc compatibility on the TV.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${MB230_DOCKER_IMAGE:-ubuntu:16.04}"
CROSS_CC="${CROSS_CC:-arm-linux-gnueabihf-gcc}"
CROSS_STRIP="${CROSS_STRIP:-arm-linux-gnueabihf-strip}"

cd "$SCRIPT_DIR"

echo "[mb230-hello] building hello in Docker ($IMAGE)..."
docker run --rm \
  -v "$SCRIPT_DIR":/w \
  -w /w \
  "$IMAGE" \
  sh -c "apt-get update -qq && \
         apt-get install -y -qq gcc-arm-linux-gnueabihf file >/dev/null 2>&1 && \
         $CROSS_CC -O2 -marm -mfloat-abi=hard -static hello.c -o hello && \
         $CROSS_STRIP hello 2>/dev/null || true && \
         file hello"

echo "[mb230-hello] done: $SCRIPT_DIR/hello"
