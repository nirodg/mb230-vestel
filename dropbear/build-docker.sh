#!/usr/bin/env bash
set -euo pipefail

# Build Dropbear SSH server/client tools for Vestel MB230 TV
# (ARMv7 hard-float, 32-bit, Linux 4.9, glibc 2.23 userspace on stock firmware).
# Produces statically-linked binaries: dropbear, dropbearkey, dbclient, scp.
#
# Usage:
#   ./build-docker.sh                # download & build default version
#   DROPBEAR_VERSION=2026.94 ./build-docker.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="${DROPBEAR_VERSION:-2026.94}"
IMAGE="${MB230_DOCKER_IMAGE:-ubuntu:16.04}"
CROSS_CC="${CROSS_CC:-arm-linux-gnueabihf-gcc}"
CROSS_STRIP="${CROSS_STRIP:-arm-linux-gnueabihf-strip}"
TARBALL="dropbear-${VERSION}.tar.bz2"
URL="https://matt.ucc.asn.au/dropbear/releases/${TARBALL}"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"

mkdir -p "$SCRIPT_DIR/out"

if [ ! -f "$SCRIPT_DIR/$TARBALL" ]; then
  echo "[dropbear] downloading $URL"
  curl -fL --retry 3 -o "$SCRIPT_DIR/$TARBALL" "$URL"
fi

echo "[dropbear] building dropbear ${VERSION} for ARMv7 hard-float in Docker ($IMAGE)..."
docker run --rm \
  -e VERSION="$VERSION" \
  -e TARBALL="$TARBALL" \
  -e CROSS_CC="$CROSS_CC" \
  -e CROSS_STRIP="$CROSS_STRIP" \
  -e JOBS="$JOBS" \
  -v "$SCRIPT_DIR":/w \
  -w /w \
  "$IMAGE" \
  bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  gcc-arm-linux-gnueabihf make bzip2 ca-certificates file >/dev/null

rm -rf "build-src"
mkdir -p build-src
tar -xjf "$TARBALL" -C build-src --strip-components=1
cd build-src

# Static ARM build. Disable features that are problematic/unneeded on the TV.
# zlib is disabled to avoid cross-lib dependency hassles (compression not critical).
# Note: do not set LDFLAGS=-static for configure (can break cross-compile checks);
# pass it to make instead.
export CC="$CROSS_CC"
export CFLAGS="-O2 -marm -mfloat-abi=hard"
./configure \
  --host=arm-linux-gnueabihf \
  --disable-zlib \
  --disable-wtmp \
  --disable-wtmpx \
  --disable-utmp \
  --disable-utmpx \
  --disable-lastlog \
  --disable-loginfunc \
  --disable-pututline \
  --disable-pututxline \
  --disable-syslog

make -j"$JOBS" PROGRAMS="dropbear dropbearkey dbclient scp" LDFLAGS="-static"
$CROSS_STRIP dropbear dropbearkey dbclient scp || true

cp dropbear dropbearkey dbclient scp /w/out/
file /w/out/dropbear /w/out/dropbearkey /w/out/dbclient /w/out/scp
'

echo "[dropbear] binaries:"
ls -lh "$SCRIPT_DIR"/out/dropbear "$SCRIPT_DIR"/out/dropbearkey "$SCRIPT_DIR"/out/dbclient "$SCRIPT_DIR"/out/scp
file "$SCRIPT_DIR"/out/dropbear
echo "[dropbear] done. Copy out/* to the TV (e.g. /tmp or /conf/dropbear)."
