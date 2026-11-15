#!/usr/bin/env bash
set -euo pipefail

# Build gui-hello-world/gui_hello for MB230 (ARMv7 hard-float, static) using Docker.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${MB230_DOCKER_IMAGE:-ubuntu:16.04}"
CROSS_CC="${CROSS_CC:-arm-linux-gnueabihf-gcc}"
CROSS_STRIP="${CROSS_STRIP:-arm-linux-gnueabihf-strip}"

cd "$SCRIPT_DIR"

echo "[mb230-gui-hello] building gui_hello in Docker ($IMAGE)..."
docker run --rm \
  -v "$SCRIPT_DIR":/w \
  -w /w \
  "$IMAGE" \
  sh -c "apt-get update -qq && \
         apt-get install -y -qq gcc-arm-linux-gnueabihf file >/dev/null 2>&1 && \
         $CROSS_CC -O2 -marm -mfloat-abi=hard -static gui_hello.c -o gui_hello && \
         $CROSS_STRIP gui_hello 2>/dev/null || true && \
         file gui_hello"

echo "[mb230-gui-hello] done: $SCRIPT_DIR/gui_hello"
