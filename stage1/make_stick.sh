#!/usr/bin/env bash
#
# make_stick.sh — build the OpenTV Stage-1 payload and stage it onto a
# FAT32 USB stick so the Vestel MB230 recognizes and (on a USB-run boot)
# executes it.  One command does: build T0 + T2, verify the ABI matches
# the TV, lay out board/, copy to the stick, and print a GO/NO-GO report.
#
#   ./make_stick.sh [/media/you/STICK]      # build + stage to the stick
#   ./make_stick.sh --build-only            # just build into board/
#   ./make_stick.sh --help
#
# Nothing here writes to the TV.  The stick stays a plain FAT32 volume:
# board/run.sh is read-only to NAND by design (see run.sh).  REVERSIBLE.
#
# WHY THIS SCRIPT EXISTS
#   * T2 (opentv_launcher) MUST be linked against glibc <= 2.23 — the TV's
#     rootfs ships glibc 2.23.  A modern host toolchain silently needs
#     GLIBC_2.34 and the binary dies before main() on the TV, which looks
#     exactly like a GPU failure.  We therefore build T2 inside an
#     ubuntu:16.04 container (gcc 5.4 / glibc 2.23) unless the host
#     toolchain is already old enough, and we REFUSE to stage a T2 that
#     needs a newer glibc.
#   * T0 (opentv_fbshow) is static libc, so any ARM toolchain works.
#
set -euo pipefail

# ---------------------------------------------------------------- config
HERE=$(cd "$(dirname "$0")" && pwd)       # stage1/
LAUNCHER="$HERE/launcher"
BOARD="$HERE/board"
SYSROOT="${SYSROOT:-$LAUNCHER/stocklibs}"
TV_GLIBC_MINOR="${TV_GLIBC_MINOR:-23}"    # MB230 rootfs = glibc 2.23
BUILD_IMAGE="${BUILD_IMAGE:-ubuntu:16.04}"
CROSS="${CROSS_COMPILE:-arm-linux-gnueabihf-}"

BUILD_ONLY=0
STICK=""

c_red=$'\033[31m'; c_grn=$'\033[32m'; c_yel=$'\033[33m'; c_rst=$'\033[0m'
ok()   { printf '%s[ ok ]%s %s\n'   "$c_grn" "$c_rst" "$*"; }
warn() { printf '%s[warn]%s %s\n'   "$c_yel" "$c_rst" "$*"; }
die()  { printf '%s[FAIL]%s %s\n'   "$c_red" "$c_rst" "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }

usage() { sed -n '2,25p' "$0"; exit 0; }

for a in "$@"; do
    case "$a" in
        --help|-h) usage ;;
        --build-only) BUILD_ONLY=1 ;;
        --*) die "unknown flag: $a" ;;
        *) STICK="$a" ;;
    esac
done

# --------------------------------------------------------- toolchain pick
# Decide how to build T2: native old-enough toolchain, else docker.
host_glibc_minor() {
    # minor version of the cross-toolchain's bundled libc, or 999 if n/a
    local libc
    libc=$(find /usr/"${CROSS%-}"/lib /usr/lib/"${CROSS%-}" -maxdepth 1 \
             -name 'libc-*.so' 2>/dev/null | head -1 || true)
    [ -n "$libc" ] || { echo 999; return; }
    basename "$libc" | sed -E 's/libc-2\.([0-9]+)\.so/\1/;t;s/.*/999/'
}

T2_IN_DOCKER=1
if command -v "${CROSS}gcc" >/dev/null 2>&1; then
    hm=$(host_glibc_minor)
    if [ "$hm" -le "$TV_GLIBC_MINOR" ] 2>/dev/null; then
        T2_IN_DOCKER=0
        ok "host ${CROSS}gcc uses glibc 2.$hm (<= TV 2.$TV_GLIBC_MINOR) — building T2 natively"
    else
        warn "host ${CROSS}gcc uses glibc 2.$hm (> TV 2.$TV_GLIBC_MINOR) — will build T2 in $BUILD_IMAGE"
    fi
else
    warn "no host ${CROSS}gcc — will build T2 in $BUILD_IMAGE"
fi

if [ "$T2_IN_DOCKER" -eq 1 ] && ! command -v docker >/dev/null 2>&1; then
    die "need either an ARM toolchain with glibc <= 2.$TV_GLIBC_MINOR, or docker for $BUILD_IMAGE"
fi

# ----------------------------------------------------------------- build
step "Build T0 (opentv_fbshow, static ARM — any toolchain)"
if [ "$T2_IN_DOCKER" -eq 0 ]; then
    make -C "$LAUNCHER" fbshow
else
    docker run --rm -v "$LAUNCHER":/w -w /w "$BUILD_IMAGE" bash -c '
        set -e
        apt-get update -qq >/dev/null
        apt-get install -y -qq gcc-arm-linux-gnueabihf make file binutils >/dev/null
        make fbshow' \
    && docker run --rm -v "$LAUNCHER":/w alpine chown "$(id -u):$(id -g)" /w/opentv_fbshow >/dev/null 2>&1 || true
fi
[ -f "$LAUNCHER/opentv_fbshow" ] || die "T0 build produced no binary"

step "Build T2 (opentv_launcher, GLES2 via stock libmali, glibc 2.$TV_GLIBC_MINOR)"
if [ ! -f "$SYSROOT/lib/libmali.so" ]; then
    warn "no $SYSROOT/lib/libmali.so — T2 will be SKIPPED."
    warn "Assemble the BYO sysroot first (see launcher/Makefile header), then re-run."
    SKIP_T2=1
else
    SKIP_T2=0
    if [ "$T2_IN_DOCKER" -eq 0 ]; then
        make -C "$LAUNCHER" launcher SYSROOT="$SYSROOT" TV_GLIBC_MINOR="$TV_GLIBC_MINOR"
        "${CROSS}strip" "$LAUNCHER/opentv_launcher" 2>/dev/null || true
    else
        docker run --rm -v "$LAUNCHER":/w -w /w "$BUILD_IMAGE" bash -c "
            set -e
            apt-get update -qq >/dev/null
            apt-get install -y -qq gcc-arm-linux-gnueabihf make file binutils >/dev/null
            make launcher SYSROOT='${SYSROOT#$LAUNCHER/}' TV_GLIBC_MINOR='$TV_GLIBC_MINOR'
            arm-linux-gnueabihf-strip opentv_launcher"
        docker run --rm -v "$LAUNCHER":/w alpine chown "$(id -u):$(id -g)" /w/opentv_launcher >/dev/null 2>&1 || true
    fi
    [ -f "$LAUNCHER/opentv_launcher" ] || die "T2 build produced no binary"
fi

# ---------------------------------------------------------------- verify
# Fail LOUD here rather than let the TV show a blank screen with no clue.
verify_arm() {
    file "$1" | grep -q 'ELF 32-bit LSB .*ARM, EABI5' \
        || die "$(basename "$1") is not an ARM EABI5 ELF"
}
verify_glibc() {
    local max
    max=$(readelf -V "$1" 2>/dev/null | grep -Eo 'GLIBC_2\.[0-9]+' \
            | sed 's/GLIBC_2\.//' | sort -n | tail -1)
    max=${max:-0}
    [ "$max" -le "$TV_GLIBC_MINOR" ] \
        || die "$(basename "$1") needs glibc 2.$max > TV 2.$TV_GLIBC_MINOR — rebuild with $BUILD_IMAGE"
    echo "$max"
}

step "Verify the binaries match the TV (ARMv7 EABI5, glibc <= 2.$TV_GLIBC_MINOR)"
verify_arm "$LAUNCHER/opentv_fbshow"
if file "$LAUNCHER/opentv_fbshow" | grep -q 'statically linked'; then
    ok "T0 opentv_fbshow: ARM EABI5, static (no glibc dependency)"
else
    g=$(verify_glibc "$LAUNCHER/opentv_fbshow"); ok "T0 opentv_fbshow: ARM EABI5, needs <= glibc 2.$g"
fi
if [ "${SKIP_T2:-1}" -eq 0 ]; then
    verify_arm "$LAUNCHER/opentv_launcher"
    g=$(verify_glibc "$LAUNCHER/opentv_launcher")
    need=$(readelf -d "$LAUNCHER/opentv_launcher" | sed -n 's/.*Shared library: \[\(.*\)\]/\1/p' | paste -sd, -)
    ok "T2 opentv_launcher: ARM EABI5, needs <= glibc 2.$g; NEEDED=$need"
    echo "$need" | grep -q 'libmali.so' \
        || warn "T2 does not list libmali.so as NEEDED — check the link"
fi

# ------------------------------------------------------ assemble board/
step "Assemble board/ payload"
mkdir -p "$BOARD"
cp -f "$LAUNCHER/opentv_fbshow" "$BOARD/opentv_fbshow"
[ "${SKIP_T2:-1}" -eq 0 ] && cp -f "$LAUNCHER/opentv_launcher" "$BOARD/opentv_launcher"
[ -f "$BOARD/run.sh" ] || die "missing $BOARD/run.sh (the loader) — not generated here"
chmod +x "$BOARD"/run.sh "$BOARD"/opentv_fbshow "$BOARD"/opentv_launcher 2>/dev/null || true
sh -n "$BOARD/run.sh" || die "run.sh has a shell syntax error"
ok "board/ contents:"; ls -l "$BOARD" | sed 's/^/        /'

if [ "$BUILD_ONLY" -eq 1 ]; then
    step "Build-only: skipping stick copy"
    ok "Payload ready in $BOARD — copy board/ to <FAT32 stick>/board/"
    exit 0
fi

# ----------------------------------------------------------- stage stick
if [ -z "$STICK" ]; then
    # Offer FAT32 removable mounts under /media/$USER as candidates.
    mapfile -t cands < <(find /media/"$USER" -maxdepth 1 -mindepth 1 -type d 2>/dev/null || true)
    [ "${#cands[@]}" -eq 1 ] && STICK="${cands[0]}"
    [ -n "$STICK" ] || die "no stick path given and could not auto-detect one (pass it as an argument)"
    warn "auto-detected stick: $STICK"
fi
[ -d "$STICK" ] || die "stick path not a directory: $STICK"

# Confirm it is really FAT/VFAT — the MB230 only reads FAT32 sticks.
fstype=$(findmnt -n -o FSTYPE --target "$STICK" 2>/dev/null || true)
case "$fstype" in
    vfat|msdos|exfat) ok "stick filesystem: $fstype" ;;
    "") warn "could not determine stick filesystem (findmnt unavailable)" ;;
    *) die "stick is $fstype, but the MB230 needs FAT32 (vfat). Reformat as FAT32." ;;
esac
[ "$fstype" = exfat ] && warn "exFAT seen — the MB230 wants FAT32 specifically; reformat if the TV ignores it."

step "Stage board/ onto $STICK"
mkdir -p "$STICK/board"
cp -f "$BOARD/run.sh"         "$STICK/board/run.sh"
cp -f "$BOARD/opentv_fbshow"  "$STICK/board/opentv_fbshow"
[ "${SKIP_T2:-1}" -eq 0 ] && cp -f "$BOARD/opentv_launcher" "$STICK/board/opentv_launcher"
sync
ok "copied; verifying hashes match repo board/"
fail=0
for f in run.sh opentv_fbshow $([ "${SKIP_T2:-1}" -eq 0 ] && echo opentv_launcher); do
    a=$(sha256sum "$BOARD/$f" | cut -d' ' -f1)
    b=$(sha256sum "$STICK/board/$f" | cut -d' ' -f1)
    if [ "$a" = "$b" ]; then printf '        %s  %s\n' "$a" "$f"
    else warn "HASH MISMATCH on $f (repo $a vs stick $b)"; fail=1; fi
done
[ "$fail" -eq 0 ] || die "stick copy did not verify — do not trust this stick"

# --------------------------------------------------------------- report
step "GO / NO-GO"
cat <<EOF
  Stick staged: $STICK/board/  (FAT32: ${fstype:-unknown})
  Payload:      T0 opentv_fbshow$([ "${SKIP_T2:-1}" -eq 0 ] && echo " + T2 opentv_launcher")
  Loader:       run.sh (read-only to NAND; logs to the stick)

  TO RUN ON THE TV — the stock firmware only runs board/run.sh on the
  "Run AP from USB" boot path, so the stick must be present BEFORE boot:
    1. Insert this stick.
    2. Power-cycle the TV at the mains (not standby) — the auto-run check
       happens once, early in boot.
    3. Watch for a T0 colour pattern, then (if built) the T2 triangle.
    4. Pull the stick, re-run this host, and read opentv_stage1.log
       that run.sh wrote to the stick root.

  If NO opentv_stage1.log appears, run.sh never executed (the firmware
  took "Run AP from FLASH"); fall back to the /conf/remote.txt dev path
  documented in OPENTV.md — not a payload problem.
EOF
ok "done"
