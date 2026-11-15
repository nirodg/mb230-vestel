#!/bin/sh
# Helper to run gui_hello on the TV as a takeover test (intended to run ON THE TV).
# WARNING: this stops aurora/idtv to give this app exclusive display/input access.
# The stock UI will stop; recover by rebooting (power cycle) or restarting services.
#
# Upload gui_hello and this script to /tmp, then:
#   chmod +x /tmp/gui_hello /tmp/run-on-tv.sh
#   /tmp/run-on-tv.sh

APP="${APP:-/tmp/gui_hello}"

echo "[run-on-tv] stopping stock UI (aurora/idtv/appmgr) to free display+input..."
# Try to stop common processes; adjust if needed on your firmware.
killall aurora.elf 2>/dev/null
killall idtv 2>/dev/null
killall com.nvt.idtv 2>/dev/null
killall appmgr 2>/dev/null
sleep 2

echo "[run-on-tv] starting $APP (Ctrl-C in this session to stop app)"
echo "[run-on-tv] if screen/input is stuck after exit, reboot the TV."
exec "$APP"
