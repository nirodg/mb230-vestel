#!/bin/sh
# Best-effort remote/IR button event monitor for Vestel MB230 (runs on TV).
# Upload via telnet (wget/nc), chmod +x, run as root.
#
# Notes:
# - Stock IR is handled in userspace via DirectFB nvt_uart_ir on /dev/ttyS2 and /dev/ntgpio.
# - /dev/ttyS2 may already be read by aurora/other processes; passive reads can miss events
#   or (if you change tty settings) interfere with normal remote input. Use with care.
# - This script shows raw bytes/hex seen on candidate interfaces; mapping raw data to
#   key names may require correlating with presses.

DEV_TTY="${DEV_TTY:-/dev/ttyS2}"
DEV_GPIO="${DEV_GPIO:-/dev/ntgpio}"
OUTDIR="${OUTDIR:-/tmp/ir-monitor}"
DUR="${DUR:-0}"   # seconds, 0 = run until Ctrl-C

mkdir -p "$OUTDIR"
echo "[ir-monitor] output dir: $OUTDIR"
echo "[ir-monitor] tty=$DEV_TTY gpio=$DEV_GPIO dur=${DUR}s (0=forever)"
echo "[ir-monitor] press buttons now (Ctrl-C to stop if dur=0)"
date 2>/dev/null || true

# Show holders of interesting devices (informational)
echo "[ir-monitor] device holders:"
for p in /proc/[0-9]*/fd; do
  pid=${p#/proc/}; pid=${pid%/fd}
  for f in "$p"/*; do
    t=$(readlink "$f" 2>/dev/null) || continue
    case "$t" in
      *ttyS2|*ntgpio) echo "  pid=$pid fd=$(basename "$f") -> $t  cmd=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)";;
    esac
  done
done 2>/dev/null

cleanup() {
  echo
  echo "[ir-monitor] stopping..."
  [ -n "$P_TTY" ] && kill "$P_TTY" 2>/dev/null
  [ -n "$P_GPIO" ] && kill "$P_GPIO" 2>/dev/null
  [ -n "$P_RAW" ] && kill "$P_RAW" 2>/dev/null
  wait 2>/dev/null
  echo "[ir-monitor] logs: $OUTDIR/ttyS2.hex $OUTDIR/ntgpio.hex $OUTDIR/ttyS2.raw"
  exit 0
}
trap cleanup INT TERM

# Try to snapshot tty settings (read-only info)
if command -v stty >/dev/null 2>&1; then
  echo "[ir-monitor] stty -F $DEV_TTY (before):"
  stty -F "$DEV_TTY" -a 2>&1 | head -20
fi

# Reader 1: hexdump stream from ttyS2 as-is
(
  echo "[ttyS2 hexdump start $(date 2>/dev/null)]"
  # line-buffered-ish: hexdump outputs as data arrives
  cat "$DEV_TTY" 2>/dev/null | while IFS= read -r -n1 c 2>/dev/null || [ -n "$c" ]; do
    :
  done
) >/dev/null 2>&1 &
# Fallback/simple hexdump pipeline
(cat "$DEV_TTY" 2>/dev/null | hexdump -v -e '1/1 "%02x " "\n"' >> "$OUTDIR/ttyS2.hex") &
P_TTY=$!

# Reader 2: try ntgpio as byte stream (may exit immediately if unsupported)
(cat "$DEV_GPIO" 2>/dev/null | hexdump -v -e '1/1 "%02x " "\n"' >> "$OUTDIR/ntgpio.hex") &
P_GPIO=$!

# Reader 3: also try raw binary capture from ttyS2
(cat "$DEV_TTY" 2>/dev/null >> "$OUTDIR/ttyS2.raw") &
P_RAW=$!

# Live display loop: tail new hex bytes if any
echo "[ir-monitor] live view (hex bytes per line as received; may be empty if driver consumes events):"
LAST_T=0
LAST_G=0
start_ts=$(date +%s 2>/dev/null || echo 0)
while :; do
  if [ -s "$OUTDIR/ttyS2.hex" ]; then
    sz=$(wc -c < "$OUTDIR/ttyS2.hex" 2>/dev/null || echo 0)
    if [ "$sz" != "$LAST_T" ]; then
      echo "--- ttyS2 @ $(date 2>/dev/null) ---"
      tail -c +$((LAST_T+1)) "$OUTDIR/ttyS2.hex" 2>/dev/null | tr '\n' ' ' | sed 's/  */ /g'; echo
      LAST_T=$sz
    fi
  fi
  if [ -s "$OUTDIR/ntgpio.hex" ]; then
    sz=$(wc -c < "$OUTDIR/ntgpio.hex" 2>/dev/null || echo 0)
    if [ "$sz" != "$LAST_G" ]; then
      echo "--- ntgpio @ $(date 2>/dev/null) ---"
      tail -c +$((LAST_G+1)) "$OUTDIR/ntgpio.hex" 2>/dev/null | tr '\n' ' ' | sed 's/  */ /g'; echo
      LAST_G=$sz
    fi
  fi
  if [ "$DUR" != "0" ]; then
    now=$(date +%s 2>/dev/null || echo 0)
    [ $((now - start_ts)) -ge "$DUR" ] && cleanup
  fi
  sleep 1
done
