# OpenTV Stage 1 — bootable USB PoC

**Goal:** prove our own userland can take over the screen on the TV,
launched from a USB stick, **writing nothing to the TV**. Pull the stick
→ the TV is exactly as before.

## What "bootable" means here
The MB230 has secure boot + proprietary XBOOT, so it will **not** boot an
arbitrary kernel from USB like a PC live-USB. Instead we ride the stock
firmware's factory path: the stock signed kernel + rootfs boot normally
and load the GPU drivers, then `/usr/script/startup.sh` auto-runs
`/media/sda[1]/board/run.sh` from an inserted FAT32 stick. That script
(ours) launches our program. Reversible, no reflash.

## Validation ladder (any rung = "it works")
First boot does **not** need the GPU. Climb cheapest -> richest; each
rung alone validates that our userland runs from USB and owns the screen:

- **T0 - framebuffer picture** (`opentv_fbshow`, plain libc -> `/dev/fb0`,
  no vendor libs): a colour pattern (or a raw image) on the panel.
- **T1 - console / shell on screen**: a Busybox `getty`/`sh` on the
  framebuffer console. A "classic shell" or minimal desktop here is
  enough.
- **T2 - GPU reuse** (`opentv_launcher`, EGL/fbdev GLES2 -> stock
  `libmali.so`): a triangle. Unblocks the real compositor/UI.

`board/run.sh` auto-runs **T0 first, then T2** if both are on the stick.

## Build (on your PC)
Toolchain: `sudo apt install gcc-arm-linux-gnueabihf`

```
cd stage1/launcher
make fbshow                      # T0 - needs nothing from the TV
# T2 (optional, later): assemble a BYO sysroot from your TV dump first:
#   stocklibs/include/EGL/*.h  stocklibs/include/GLES2/*.h   (Khronos headers)
#   stocklibs/lib/libEGL.so    stocklibs/lib/libGLESv2.so    (from ap0/lib)
make launcher SYSROOT=./stocklibs
```
`stocklibs/` and any `*.so` are **git-ignored - never commit vendor
blobs.** The repo is verified to build on a normal PC (fbshow with libc;
the launcher's EGL/GLES2 code links against desktop Mesa for host dev).

## Assemble the USB stick (FAT32)
```
<USB>/board/
    run.sh            <- stage1/board/run.sh
    opentv_fbshow     <- from make fbshow   (T0)
    opentv_launcher   <- from make launcher (T2, optional)
```
```
cp stage1/board/run.sh            <USB>/board/
cp stage1/launcher/opentv_fbshow  <USB>/board/     # and opentv_launcher if built
```
Optional custom T0 image: put a raw full-width BGRA file on the stick and
set `OPENTV_IMG=myimage.raw`, else fbshow draws a test pattern.

## Run on the TV & read the result
1. Insert the FAT32 stick, **power-cycle** the TV.
2. Expected: T0 colour pattern, then (if built) the T2 triangle.
3. **Pull the stick, read `opentv_stage1.log` on your PC** - the loader
   writes its log to the stick itself (no network/serial needed). It
   records `/dev` node presence, libmali path, and which rung ran.

## Go/No-Go (from the log + screen)
- **GO:** a picture/triangle on the panel -> our userland owns the screen
  from USB; Stage 2 unblocked.
- **T0 ok, T2 fails** (`eglCreateWindowSurface` error in log): the Mali
  `fbdev_window` contract differs - adjust the native-window struct.
- **MISSING /dev/fb0**: stock display not up when we ran - increase the
  wait in run.sh.
- **Nothing / no log on stick**: the factory USB-run path didn't trigger
  - confirm FAT32, the `board/` dir name, and that the TV runs AP from
  USB (see `../ARCHITECTURE.md`, startup.sh path).

## Safety
`run.sh` contains no `nand`/`sf`/`mount -o rw`. Stage 1 stays read-only
to the TV. Keep it that way.
