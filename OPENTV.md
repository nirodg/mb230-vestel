# OpenTV — Plan / Spec

An open-source, lightweight Linux TV experience for the Vestel MB230
(Novatek NT72671). Reuse the proprietary driver/middleware `.so` blobs
**as-is** (no decompilation); build our own userland and UI on top.
Evidence basis: `ARCHITECTURE.md` (MD30010 static analysis).

## Why not Android
32-bit ARMv7 (Android dropped 32-bit after 11), no public NT72671
BSP/HAL, binary-only drivers tied to Linux 4.9, ~800 MB RAM, and DRM
signing that custom builds lose. Not viable — go custom Linux instead.

## Hard constraint
Secure boot + `nvt_sign` + proprietary XBOOT ⇒ we **cannot** boot our
own kernel/bootloader without Novatek signing keys. So "live boot" means
riding the **stock signed kernel + rootfs**, then taking over userland —
not replacing the boot chain.

## Stage 1 — Live PoC (zero writes to the TV)
Boot stock firmware, then hijack the factory **"run AP from USB"** path
(`/usr/script/startup.sh` → `/media/sda[1]/board/run.sh`) to launch our
own launcher instead of `aurora.elf`. Keep `/vendor` + `/vendor2`
mounted and reuse proprietary libs via `LD_LIBRARY_PATH`/`dlopen`.
Fallback/dev channel: the `/conf/remote.txt` gdbserver+CIFS path.
Goal: our process draws to the framebuffer/Mali and takes remote input,
on hardware, reversibly. Success = **any** sign of our userland owning the screen with nothing
written to NAND: a framebuffer picture (T0), a shell/lightweight desktop
on the panel (T1), or the GLES launcher (T2). See `stage1/`.

## Stage 2 — Minimal usable system
Map the reusable surface: display/compositor (`fb*`, `mali0`, `ndppq`),
input (remote/CEC), audio, tuner/HDMI — which `.so`s + ioctl/char-dev
contracts each needs, treated as black boxes. Build a thin Buildroot/
Yocto userland (or overlay on the stock rootfs) that boots to a simple
launcher reusing those blobs. Decide: USB-run only, or a signed-image
route if keys/exploit ever surface.

## Stage 3 — "OpenTV" UI
A proper launcher/compositor (Android-TV / Apple-TV feel): apps grid,
settings, input switching, media playback via reused codecs. Own design,
own code; proprietary blobs stay as leaf drivers behind our own API
shims.

## Architecture: portable core + device porting layer (CyanogenMod model)
Split OpenTV into (a) a **device-independent core** (compositor, launcher,
UI, app model) written against our **own stable internal APIs**, and
(b) a per-device **porting layer** that implements those APIs by wrapping
the proprietary blobs (`libmali` for GL, UART-IR for input, and later
tuner/audio/HDMI/DRM). Porting to a new TV = rewrite only layer (b),
exactly like CyanogenMod/LineageOS device trees + vendor blobs. The core
builds and runs on host/Mesa; the MB230 porting layer binds the stock
`.so`s on the TV.

## "Bootable USB" — what's actually achievable
Secure boot + XBOOT mean **no custom kernel from USB** (not a PC-style
live-USB). The deliverable is a FAT32 stick whose `board/run.sh` the
**stock firmware auto-runs** after its signed kernel/rootfs boot — our
userland takes over, reusing the already-loaded GPU. See `stage1/` for
the loader, the GLES2 PoC launcher, and the stick layout. Reversible; no
reflash.

## Licensing & vendor blobs (BYO — non-negotiable)
OpenTV is a reusable, manufacturer-agnostic base. This repo contains
**only our original code**. We **never** vendor, commit, redistribute, or
decompile proprietary device libraries — producing or shipping those is
not our job. A porter **brings their own** TV's libraries (here:
`libmali.so`, UART-IR, tuner/audio/DRM blobs), which stay on-device and
are reused in place at runtime. Build sysroots, `stocklibs/`, and any
`*.so` are git-ignored so a vendor blob can't be committed by accident.
This keeps the project clean of third-party copyright.

## Principles
- No writes to flash until a stage explicitly needs it (Stage 1–2 stay
  USB-only / reversible).
- Proprietary blobs are **used, never decompiled**: wrap them behind our
  own interfaces; record each lib's observed contract, not its internals.
- Don't touch secure boot, SECOS, or the signed `nvt_sign` volume.
- DRM (PlayReady/Marlin) is out of scope — expect no protected playback.

## Stage 1 feasibility — graphics (RESOLVED: GO)
Static check of the stock `ap0` libs:
- `libmali.so` (8.6 MB) is **self-contained**: it needs only
  libc/libdl/libpthread/librt/libm/libstdc++/libgcc — **no NVT
  middleware**. Exports the full **EGL + GLES** (1131 funcs). So a small
  custom app can reuse the GPU **without** dragging in `aurora.elf`'s
  135-lib monolith or DirectFB.
- `libEGL.so` / `libGLESv2.so` are 3-function **shim wrappers** over
  `libmali.so` → the GUI just links `-lEGL -lGLESv2`.
- Mali build config (from the blob): `winsys=['fbdev']`,
  `wayland_backend=fbdev`, `os=linux`, `platform_config=nvt`,
  `gles32=1`, `vulkan=0`, `gpu=tSIx`, `hwver=r1p1`, dma-buf on.
  → **Native surface = EGL on fbdev** (`/dev/fb0`), **GLES2/3 (up to
  3.2), no Vulkan**. Window handle is a framebuffer/`fbdev_window`, not
  GBM/X11/Wayland.
- Device nodes needed: `/dev/fb0`, `/dev/mali`, `/dev/ntkgpu` — all
  provided by stock `mali.ko` + `ntkndp*.ko`, which load during stock
  boot **before** our USB userland runs. Our live app inherits a ready
  GPU.

**Hand-off to the GUI session:** target **EGL + GLES2/GLES3 over fbdev**
(single fullscreen surface, 1920×1080 — see `PANEL_WIDTH/HEIGHT` in
`run.sh`). Anything that compiles to GLES2/3 on a raw EGL/fbdev context
(e.g. a C/C++ or Rust compositor, Skia-GL, LVGL-GL) will port; avoid
Vulkan and avoid assuming a window system.

> Note: `run.sh` runs `aurora.elf` with a large env block (FRAMEBUFFER,
> MALI_NOCLEAR, OSD plane sizes, GStreamer paths). Graphics need only the
> framebuffer + Mali nodes; the rest is TV middleware we add later.

## Stage 1 — input & loader (analyzed)
- **Remote = IR over UART**, not evdev. Decoded in userspace by DirectFB
  `libdirectfb_nvt_uart_ir.so`; app uses `/dev/ttyS0`/`/dev/ttyS2` +
  `/dev/ntgpio`; scancode→key maps in `ice_keymapping_db.xml` /
  `vk_keymapping_db.xml`. No kernel input module → reusable from our own
  process (reuse that driver, or read the UART tty + apply the keymap).
- **Mali fbdev native window:** `EGLNativeDisplayType=EGL_DEFAULT_DISPLAY`
  (Mali opens `FRAMEBUFFER=/dev/fb0`); `EGLNativeWindowType` → pointer to
  `struct fbdev_window { unsigned short width; unsigned short height; }`.
  Confirm at first bring-up.
- **Loader skeleton:** `stage1/board/run.sh` — reversible USB loader
  (reuses stock `/vendor/lib` read-only via `LD_LIBRARY_PATH`, sets the
  minimal Mali env, execs `opentv_launcher`). Writes nothing to NAND.

## Simulation without the TV (QEMU)
GPU can't be emulated: `libmali.so` needs `/dev/mali`+`/dev/ntkgpu`
(proprietary drivers on the real SoC). But EGL/GLES is a portable API —
build the GUI on host/QEMU against **Mesa EGL/GLES** behind a thin
platform shim; the same GLES code links stock `libmali.so` on the TV.
~90% off-hardware; only final GPU/panel validation needs the TV (via USB
or the network gdbserver/CIFS path — neither reflashes).

## Open unknowns (resolve early)
Can an unsigned USB userland actually `dlopen` the stock Mali/display
libs outside `aurora.elf`'s environment? What init/env does
`aurora.elf` rely on (via `run.sh`) that we must reproduce? Which
char-dev/ioctl contracts are stable? These gate Stage 1.
