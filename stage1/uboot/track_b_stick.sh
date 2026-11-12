#!/usr/bin/env bash
# Stage the USB stick for the Track-B /conf write, or for recovery.
# This only writes the STICK. The actual TV flash write happens when YOU
# boot the TV holding OK with the staged stick. Nothing here touches the TV.
#
#   track_b_stick.sh write   --ip IP --user U --pass P --dump DUMP --stick DIR
#   track_b_stick.sh restore --dump DUMP --stick DIR
#
# write:   builds remote.txt (isgdb=0) + conf_new.ubifs (current /conf +
#          remote.txt), stages conf_new.ubifs + the original dump (restore
#          image) + an armed kylo_usb_update.scr that `ubi write`s apdat0.
# restore: stages the original dump + an armed kylo_usb_update.scr that raw
#          nand-writes apdat0 back (byte-exact rollback).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-}"; shift || true
IP= USER_= PASS= DUMP= STICK=
while [ $# -gt 0 ]; do case "$1" in
  --ip) IP="$2"; shift 2;; --user) USER_="$2"; shift 2;; --pass) PASS="$2"; shift 2;;
  --dump) DUMP="$2"; shift 2;; --stick) STICK="$2"; shift 2;;
  *) echo "unknown arg: $1"; exit 1;; esac; done
[ -n "$DUMP" ] && [ -f "$DUMP" ] || { echo "need --dump <original apdat0 dump>"; exit 1; }
[ -n "$STICK" ] && [ -d "$STICK" ] || { echo "need --stick <mounted FAT32 dir>"; exit 1; }
fstype=$(findmnt -n -o FSTYPE --target "$STICK" 2>/dev/null || true)
case "$fstype" in vfat|msdos) ;; *) echo "stick is '$fstype', need FAT32 (vfat)"; exit 1;; esac

hexsize(){ printf '0x%x' "$(stat -c %s "$1")"; }

case "$MODE" in
write)
  [ -n "$IP" ] && [ -n "$USER_" ] && [ -n "$PASS" ] || { echo "write needs --ip --user --pass"; exit 1; }
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  printf '0:%s:%s:%s\n' "$IP" "$USER_" "$PASS" > "$tmp/remote.txt"
  echo "[*] remote.txt -> 0:$IP:$USER_:****  (isgdb=0, run aurora.elf directly)"
  "$HERE/make_conf_image.sh" "$DUMP" "$tmp/remote.txt" "$tmp/conf_new.ubifs"
  SZ=$(hexsize "$tmp/conf_new.ubifs")
  sed -e "s/__IMG_NAME__/conf_new.ubifs/" -e "s/__IMG_SIZE_HEX__/$SZ/" \
      "$HERE/conf_write.scr.TEMPLATE" > "$tmp/kylo_usb_update.scr"
  cp -f "$tmp/conf_new.ubifs" "$STICK/conf_new.ubifs"
  cp -f "$DUMP" "$STICK/dump_apdat0.bin"                 # restore image kept alongside
  cp -f "$tmp/kylo_usb_update.scr" "$STICK/kylo_usb_update.scr"
  sync
  echo "[ok] WRITE stick staged at $STICK (img size $SZ)."
  echo "     Boot holding OK to perform the /conf write. Restore image is on the stick."
  ;;
restore)
  sed -e "s/__.*__//g" "$HERE/conf_restore.scr.TEMPLATE" > "$STICK/kylo_usb_update.scr"
  cp -f "$DUMP" "$STICK/dump_apdat0.bin"
  sync
  echo "[ok] RESTORE stick staged at $STICK. Boot holding OK to roll /conf back."
  ;;
*) echo "usage: track_b_stick.sh write|restore ..."; exit 1;;
esac

echo "[i] destructive-op audit of staged .scr:"
grep -vE '^\s*#|^\s*$' "$STICK/kylo_usb_update.scr" | grep -nE 'nand (erase|write)|ubi write|sf (erase|write)' || true
echo "[i] (all writes must be confined to apdat0 @0xe340000 / volume apdat0)"
