#!/usr/bin/env bash
# Rebuild the MB230 /conf (apdat0) UBIFS = the device's CURRENT contents
# + a tiny hook file (remote.txt), for a whole-volume `ubi write` via the
# U-Boot .scr channel. See OPENTV.md "Stage 2 - code-execution surface".
#
# This DOES NOT touch the TV. It only produces an image file locally.
# Arming/writing is a separate, explicit step.
#
#   make_conf_image.sh <apdat0_dump.bin> <remote.txt> <out.ubifs>
#
# Geometry is taken from the live dump (hard-coded from analysis; a repack
# that doesn't match these will not mount on the TV):
set -euo pipefail
PEB=262144          # physical erase block
LEB=253952          # logical erase block (leb_size)
MINIO=4096          # min_io_size
MAXLEB=31           # max_leb_cnt (apdat0 reserved LEBs)
COMPR=lzo           # default_compr (1)

DUMP="${1:?apdat0 dump}"; HOOK="${2:?remote.txt}"; OUT="${3:?out.ubifs}"
command -v mkfs.ubifs >/dev/null || { echo "need mtd-utils (mkfs.ubifs)"; exit 1; }
command -v ubireader_extract_files >/dev/null || { echo "need ubi_reader"; exit 1; }

work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
echo "[*] extracting current /conf from dump ..."
ubireader_extract_files -k -o "$work/x" "$DUMP" >/dev/null 2>&1 || true
root="$(find "$work/x" -type d -name apdat0 | head -1)"
[ -n "$root" ] || { echo "could not find apdat0 root in extraction"; exit 1; }
n=$(find "$root" -type f | wc -l); echo "[*] current files: $n"

echo "[*] injecting hook: $(basename "$HOOK") -> /conf/remote.txt"
cp -f "$HOOK" "$root/remote.txt"

echo "[*] mkfs.ubifs (m=$MINIO e=$LEB c=$MAXLEB x=$COMPR) ..."
mkfs.ubifs -m "$MINIO" -e "$LEB" -c "$MAXLEB" -x "$COMPR" -r "$root" -o "$OUT"
echo "[*] built $OUT ($(stat -c %s "$OUT") bytes, $(( $(stat -c %s "$OUT") / LEB )) LEBs)"

echo "[*] VALIDATE: re-extract the new image and confirm remote.txt present ..."
ubireader_extract_files -k -o "$work/v" "$OUT" >/dev/null 2>&1 || \
  ubireader_utils_info "$OUT" >/dev/null 2>&1 || true
if find "$work/v" -name remote.txt | grep -q . ; then
  echo "[ok] remote.txt is present and readable in the rebuilt image"
else
  echo "[!!] remote.txt NOT found on re-read -- DO NOT WRITE THIS IMAGE"; exit 2
fi
echo "[done] $OUT ready. (Nothing written to the TV.)"
