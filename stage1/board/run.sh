#!/bin/sh
# OpenTV Stage-1 live loader (PROOF OF CONCEPT).
#
# Placed at <USB>/board/run.sh. The stock firmware's /usr/script/startup.sh
# auto-runs this when the TV boots the application stage from USB
# (/media/sda[1]/board/run.sh), AFTER the stock signed kernel + rootfs
# have already loaded mali.ko / ntkndp*.ko and created /dev/fb0,
# /dev/mali, /dev/ntkgpu. We reuse those; we take over userland only.
#
# REVERSIBLE: reads stock /vendor read-only, writes nothing to NAND.
# Pull the stick -> TV is untouched. Do NOT add nand/sf/mount -o rw here.

HERE=$(cd "$(dirname "$0")" && pwd)       # <USB>/board
USBROOT=$(cd "$HERE/.." && pwd)           # <USB>  (FAT32, writable)
VENDOR=/vendor                            # stock ap0 (ro squashfs), already mounted

# Log to the USB stick itself, so results are readable on a PC with no
# network/serial. Falls back to /tmp if the stick is read-only.
LOG="$USBROOT/opentv_stage1.log"
( : >>"$LOG" ) 2>/dev/null || LOG=/tmp/opentv_stage1.log
exec >"$LOG" 2>&1
echo "[opentv] ===== start $(date) ====="
echo "[opentv] HERE=$HERE USBROOT=$USBROOT"
echo "[opentv] uname: $(uname -a 2>/dev/null)"

# --- reuse the stock proprietary libs in place (no copy, no write) --------
export LD_LIBRARY_PATH="$HERE/lib:$VENDOR/lib"
export FRAMEBUFFER=/dev/fb0
export MALI_NOCLEAR=1
export MALI_MAX_WINDOW_BUFFERS=3
export PANEL_WIDTH=1920
export PANEL_HEIGHT=1080

# --- record environment evidence for the first-boot report ----------------
echo "[opentv] /dev nodes:"; for n in /dev/fb0 /dev/mali /dev/ntkgpu /dev/ttyS2; do
    [ -e "$n" ] && echo "  present $n" || echo "  MISSING $n"
done
echo "[opentv] libmali: $(ls -l $VENDOR/lib/libmali.so 2>/dev/null || echo 'not found')"

# --- T0 first: framebuffer picture, no GPU, no vendor libs ----------------
# Cheapest proof our userland owns the panel. Runs if ./opentv_fbshow exists.
if [ -x "$HERE/opentv_fbshow" ]; then
    echo "[opentv] T0: running opentv_fbshow (framebuffer picture)"
    "$HERE/opentv_fbshow" ${OPENTV_IMG:+"$HERE/$OPENTV_IMG"} &
    T0=$!
    sleep 4            # let a picture show; then move on to T2 if present
    kill $T0 2>/dev/null
fi

# --- T2: GPU reuse via stock libmali (EGL/fbdev GLES2) --------------------
if [ -x "$HERE/opentv_launcher" ]; then
    # wait up to ~12s for the GPU nodes the stock driver creates.
    # Integer sleeps only: BusyBox `sleep` on embedded builds often lacks
    # fractional-second support, and `sleep 0.2` would error out instantly
    # -> the loop would spin with no delay and exec before /dev/mali exists.
    i=0; while [ ! -e /dev/mali ] && [ $i -lt 12 ]; do sleep 1; i=$((i+1)); done
    [ -e /dev/mali ] || echo "[opentv] WARN: /dev/mali still absent after ${i}s"
    echo "[opentv] T2: exec opentv_launcher"
    exec "$HERE/opentv_launcher"
fi

# If only T0 was present, hold the picture up.
if [ -x "$HERE/opentv_fbshow" ]; then
    echo "[opentv] holding T0 picture"
    exec "$HERE/opentv_fbshow" ${OPENTV_IMG:+"$HERE/$OPENTV_IMG"}
fi

# --- T1 fallback: a shell/console on the framebuffer -----------------------
# Reached only when NO opentv binary is on the stick. Proves our userland at
# least owns a text console on the panel, using the stock busybox. Writes
# nothing to NAND. (The remote is UART-IR, so the shell is for visual proof;
# a login prompt on the panel is still a valid "we own the screen" result.)
for TTY in /dev/tty1 /dev/tty0 /dev/console; do
    if [ -w "$TTY" ]; then
        echo "[opentv] T1: opening a shell on $TTY"
        {   echo ""
            echo "  ===== OpenTV Stage-1 T1 ====="
            echo "  Our userland runs from USB and owns this console ($TTY)."
            echo ""
        } >"$TTY" 2>/dev/null
        setsid sh -i <"$TTY" >"$TTY" 2>&1 &
        wait
        exit 0
    fi
done

echo "[opentv] ERROR: no opentv_fbshow/opentv_launcher and no writable console"
exit 1
