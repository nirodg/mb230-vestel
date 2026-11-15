#!/bin/sh
# Example launcher for Dropbear on the MB230 TV (run as root on the TV).
# Copy the dropbear/ directory contents to e.g. /conf/dropbear/ and adjust paths.
#
# Usage on TV:
#   /conf/dropbear/start-on-tv.sh

set -eu

DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
KEYDIR="${DROPBEAR_KEYDIR:-/conf/dropbear}"
PORT="${DROPBEAR_PORT:-22}"
DROPBEAR_BIN="${DROPBEAR_BIN:-$DIR/dropbear}"
DROPBEARKEY_BIN="${DROPBEARKEY_BIN:-$DIR/dropbearkey}"

# SSH needs PTYs
if ! mount | grep -q "on /dev/pts "; then
  mkdir -p /dev/pts
  mount -t devpts devpts /dev/pts 2>/dev/null || true
fi

mkdir -p "$KEYDIR"

if [ ! -f "$KEYDIR/dropbear_rsa_host_key" ]; then
  "$DROPBEARKEY_BIN" -t rsa -f "$KEYDIR/dropbear_rsa_host_key"
fi
if [ ! -f "$KEYDIR/dropbear_ed25519_host_key" ]; then
  "$DROPBEARKEY_BIN" -t ed25519 -f "$KEYDIR/dropbear_ed25519_host_key" 2>/dev/null || true
fi

# Avoid starting duplicates
if netstat -ltn 2>/dev/null | grep -q ":${PORT} " || busybox netstat -ltn 2>/dev/null | grep -q ":${PORT} "; then
  echo "dropbear/start-on-tv.sh: port ${PORT} already listening" >&2
  exit 0
fi

# Pass extra args after -- if you want to forward flags to dropbear, e.g.
#   start-on-tv.sh -- -F -E   (foreground + log to stderr)
EXTRA=""
case "${1:-}" in
  --) shift; exec "$DROPBEAR_BIN" -p "$PORT" -r "$KEYDIR/dropbear_rsa_host_key" \
        ${KEYDIR:+} "$@";;
esac

# Default: daemonize on $PORT with available host keys
if [ -f "$KEYDIR/dropbear_ed25519_host_key" ]; then
  exec "$DROPBEAR_BIN" -p "$PORT" \
    -r "$KEYDIR/dropbear_rsa_host_key" \
    -r "$KEYDIR/dropbear_ed25519_host_key"
else
  exec "$DROPBEAR_BIN" -p "$PORT" \
    -r "$KEYDIR/dropbear_rsa_host_key"
fi


