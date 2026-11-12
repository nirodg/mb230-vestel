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

set -e
HERE=$(cd "$(dirname "$0")" && pwd)       # <USB>/board
VENDOR=/vendor                            # stock ap0 (ro squashfs), already mounted
LOG=/tmp/opentv_stage1.log
exec > "$LOG" 2>&1
echo "[opentv] start $(date) from $HERE"

# --- reuse the stock proprietary libs in place (no copy, no write) --------
export LD_LIBRARY_PATH="$HERE/lib:$VENDOR/lib"
# minimal graphics env (subset of the stock run.sh)
export FRAMEBUFFER=/dev/fb0
export MALI_NOCLEAR=1
export MALI_MAX_WINDOW_BUFFERS=3
export PANEL_WIDTH=1920
export PANEL_HEIGHT=1080

# --- sanity: the GPU nodes must exist (proves stock drivers are up) --------
for n in /dev/fb0 /dev/mali /dev/ntkgpu; do
    [ -e "$n" ] || echo "[opentv] WARN missing $n (stock driver not loaded yet?)"
done
echo "[opentv] libmali: $(ls -l $VENDOR/lib/libmali.so 2>/dev/null)"

# --- launch our launcher (built elsewhere; links -lEGL -lGLESv2 -> libmali)-
#     Expected to open an EGL/fbdev GLES2 context and draw the OpenTV UI.
APP="$HERE/opentv_launcher"
if [ -x "$APP" ]; then
    echo "[opentv] exec $APP"
    exec "$APP"
else
    echo "[opentv] ERROR: $APP not found/executable — nothing to run"
    exit 1
fi
