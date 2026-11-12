# OpenTV Stage 1 — bootable USB PoC

**Goal:** prove our own userland can draw on the TV using the stock
`libmali.so`, launched from a USB stick, **writing nothing to the TV**.
Pull the stick → the TV is exactly as before.

## What "bootable" means here
The MB230 has secure boot + proprietary XBOOT, so it will **not** boot an
arbitrary kernel from USB like a PC live-USB. Instead we ride the stock
firmware's factory path: the stock signed kernel + rootfs boot normally
and load the GPU drivers, then `/usr/script/startup.sh` auto-runs
`/media/sda[1]/board/run.sh` from an inserted FAT32 stick. That script
(ours) launches our GLES launcher. Reversible, no reflash.

## USB stick layout (FAT32)
```
<USB>/
  board/
    run.sh              <- from stage1/board/run.sh (the loader)
    opentv_launcher     <- cross-compiled from stage1/launcher/
    lib/                <- (optional) our own extra .so; stock libs stay in /vendor
```
Stock proprietary libs are reused in place from `/vendor/lib` via
`LD_LIBRARY_PATH` — we do **not** copy them onto the stick.

## Build the launcher
Needs an armhf cross-toolchain and a sysroot assembled from the TV dump:
```
stage1/launcher/stocklibs/
  include/EGL/*.h  include/GLES2/*.h   # Khronos headers (egl.h, gl2.h, ...)
  lib/libEGL.so  lib/libGLESv2.so      # stock stubs copied from ap0/lib
```
```
cd stage1/launcher
make CROSS_COMPILE=arm-linux-gnueabihf- SYSROOT=./stocklibs
cp opentv_launcher ../board/opentv_launcher   # then copy board/ to the stick
```
The stubs only need to resolve EGL/GLES symbols at link time; the real
`libmali.so` resolves them at runtime from `/vendor/lib` on the TV.

**These stock `.so`/headers are BYO (bring your own) and git-ignored — do
NOT commit vendor blobs.** Copy them from your own TV's dump into
`stocklibs/` locally; the repo ships only our original code.

## Run on the TV
1. Copy `board/` to a FAT32 stick.
2. Insert, power-cycle the TV (the factory USB-run path picks it up).
3. Expected: panel shows a pulsing background + an orange triangle.
4. Logs: `/tmp/opentv_stage1.log` on the TV (readable via the gdbserver/
   CIFS dev path or a later debug dump).

## Validation ladder (any rung = "it works")
First boot does not need the GPU. Climb from cheapest to richest; each
rung on its own validates that our userland runs from USB and owns the
screen:

- **T0 — framebuffer picture** (`fbshow`, plain libc → `/dev/fb0`, no
  vendor libs): a colour pattern or raw image on the panel. Cheapest
  proof we control display output.
- **T1 — console / shell on screen**: a Busybox `getty`/`sh` on the
  framebuffer console (or serial). Proves interactive userland control.
  A "classic shell" or a minimal lightweight desktop here is enough.
- **T2 — GPU reuse** (`opentv_launcher`, EGL/fbdev GLES2 → stock
  `libmali.so`): the triangle. Unblocks the real compositor/UI.

Point `board/run.sh` at `fbshow` first, then `opentv_launcher` once T0
passes.

## Go/No-Go for the PoC
- **GO signal:** triangle renders → stock `libmali.so` is usable from our
  process; Stage 2 (real compositor/launcher) is unblocked.
- **Partial:** EGL inits but `eglCreateWindowSurface` fails → the
  `fbdev_window` contract differs; adjust the native-window struct/handle.
- **No GPU nodes:** `/dev/mali` or `/dev/ntkgpu` missing in the log →
  our script ran before the stock driver load; add a wait on those nodes.

## Safety
`board/run.sh` contains no `nand`/`sf`/`mount -o rw` — keep it that way.
Stage 1 must stay read-only to the TV.
