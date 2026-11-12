# Novatek NT72671 SoC / Vestel MB230 TV Board — Architecture

## Overview

This document summarises the SoC architecture, firmware layout and
hardware capabilities of the **Novatek NT72671** (die: **NT72673**)
found on **Vestel 17MB230** TV mainboards.  Evidence is taken directly
from the firmware image (`kylo_usb_update.bin`, DTS files, uImage
headers and kernel strings) — not from third‑party speculation.

---

## SoC: Novatek NT72673 (NT72671 family)

| Property          | Value                                  | Source                                      |
|-------------------|----------------------------------------|---------------------------------------------|
| Model string      | `Novatek NT72673`                      | DTS `/model`                                |
| ODM ID            | `72671A_TK`                            | DTS `chosen/nvt_id_str`                     |
| ISA               | **ARMv7 (32‑bit)**                     | Kernel `ARMv7 Processor`, `Linux/ARM`       |
| CPU               | **4× Cortex‑A7**                       | DTS `compatible = "arm,cortex-a7";` ×4      |
| CPU frequencies   | 500 / 700 / 900 / ~1050 MHz (turbo)    | DTS `ca53_opp` table                        |
| GPU               | **ARM Mali‑G71** (Midgard)             | DTS `compatible = "arm,mali-g71-power-model"` |
| GPU frequency     | 500 MHz                                | DTS `gpu_opp` table                         |
| RAM               | ~800 MB (272 + 528 MB contiguous banks)| DTS `memory reg`                            |
| Timer             | ARMv7 arch timer @ 12 MHz              | DTS `clock-frequency = <0xb71b00>;`         |
| PSCI              | arm,psci-1.0, method = smc             | DTS                                          |

**Correction**: The Duck.ai claim of "2× Cortex‑A73 + 2× Cortex‑A53"
is **not supported** by the firmware.  The device tree shows four
identical **Cortex‑A7** cores — a 32‑bit ARMv7 design.

---

## Boot chain

| Stage       | Name / Image                    | Format           | Details                                                                 |
|-------------|---------------------------------|------------------|-------------------------------------------------------------------------|
| 1st‑stage   | **XBOOT** (NovaTek proprietary) | raw binary       | `n33006b_nand_sboot_defconfig`, loads from NAND offset 0x0             |
| DRAM init   | **DDRCFG**                      | raw binary       | NAND 0x100000, loaded by XBOOT                                          |
| Secure OS   | **SECOS**                       | gzip uImage      | Load address 0x8000, built 2021‑09‑27                                   |
| 2nd‑stage   | **U‑Boot 2016.07**              | uncompressed     | Build `g6bd49a61 for nt7`, 2021‑07‑26, load 0x2800000                  |
| Device tree | **FDT0 / FDT1** (identical)     | uncompressed     | Build 2020‑03‑06, load 0x4800000, 72 KiB                               |
| Kernel      | **Linux 4.9.118+**              | gzip uImage      | GCC 6.1.1 Linaro, ARMv7 SMP preempt, load 0x2808000                    |
| Rootfs      | **SquashFS** inside UBI volume   | NAND UBI         | `root=/dev/ubiblock0_0 rootfstype=squashfs`                            |

The script `kylo_usb_update.scr` programs all stages from the `.bin`
file.  **XBOOT** is the first code the CPU runs; it validates and
loads DDRCFG → SECOS → U‑Boot → kernel.

---

## NAND partition layout (from update script)

| Partition        | NAND offset      | Size       | Notes                          |
|------------------|------------------|------------|---------------------------------|
| XBOOT            | `0x000000`       | 0x100000   | 1st‑stage bootloader            |
| DDRCFG           | `0x100000`       | 0x100000   | DRAM configuration              |
| XBOOTDAT         | `0x2c0000`       | 0x2000     | Panel / board config data       |
| NPT              | `0x400000`       | 0x1000     | NAND partition table            |
| MISC             | `0x4c0000`       | 0x1000     | Miscellaneous parameters        |
| SECOS            | `0x700000`       | 0x280000   | Secure OS                       |
| UBOOT            | `0x980000`       | 0x140000   | U‑Boot                          |
| FDT0             | `0xac0000`       | 0x140000   | Device tree blob (primary)      |
| FDT1             | `0xc00000`       | 0x140000   | Device tree blob (fallback)     |
| KER0             | `0xd40000`       | 0x700000   | Kernel (primary)                |
| KER1             | `0x1440000`      | 0xc00000   | Kernel (fallback)               |
| FS0              | `0x2040000`      | 0xc300000  | UBI → SquashFS rootfs           |
| APDAT0           | `0xe340000`      | 0x3c0000   | Application data                 |
| BUFFER           | `0xed40000`      | 0x1740000  | OTA / update buffer              |
| LOGO             | `0x1fd40000`     | 0x11000    | Boot logo (stripped JPEG)       |

---

## Operating system

- **Vestel Kylo** — a proprietary Linux‑based TV platform.
- Kernel: Linux 4.9.118, SMP PREEMPT, ARMv7.
- Rootfs: SquashFS (read‑only), mounted via UBI/UBIBLOCK.
- Init: `/init` (Busybox‑based or custom — not systemd, not Android).
- **Not Android.**  No Android framework, no ART runtime, no HAL layers
  for TV‑specific hardware are present in the firmware.

---

## Display & graphics

- **GPU**: Mali‑G71 with Midgard DDK; power model `mali-g71-power-model`.
- **HDMI**: 4 physical ports (HDMI‑A through HDMI‑D), hot‑plug
  detection, audio (I²S), CEC (`NTHDMI_MCU`).
- **Panel interfaces**: VX1 (eDP‑like) and LVDS, selectable via
  `xbootdat_spi_read_panel_cfg`.
- **Boot logo**: JPEG, 3840 × 2160, Exif metadata tags Vestel/pexif.

---

## DRM / Content protection

- **Marlin** (Broadband DRM): X.509 certificate chain and SAML
  assertions embedded in the firmware; root CA `seacert:vestel:drmperso`.
- **PlayReady**: Key storage area in SPI flash; the update script can
  burn PlayReady keys.
- Both are **proprietary, signing‑key protected**.  Modifying DRM-
  related blocks will likely break certification and playback.

---

## Boot arguments

```
console=ttyS0,115200 no_console_suspend earlyprintk
rootflags=nvt_security vmalloc=504M maxcpus=4 ubi.mtd=12
ubi.block=0,0 root=/dev/ubiblock0_0 rootfstype=squashfs ro
quiet init=/init rootwait
```

- UART console at 115 200 baud (could be accessible on the board).
- `maxcpus=4` confirms all four Cortex‑A7 cores are enabled.
- `nvt_security` root flag hints at proprietary integrity checks.

---

## So… could it run Android TV?

| Requirement                  | Status                                                         |
|------------------------------|----------------------------------------------------------------|
| CPU (ARMv7, 32‑bit)          | Android TV dropped 32‑bit after Android 11; would be stuck old |
| RAM (~800 MB)                | Very tight for Android; expect OOM issues                      |
| GPU (Mali‑G71)               | Good GPU, but needs a Linux 4.9‑compatible Mali driver binary  |
| Boot chain (XBOOT → SECOS)   | Proprietary; no public source or documentation                 |
| Kernel source / BSP          | Not public for NT72671                                         |
| TV hardware drivers          | Tuner, CI+, HDMI ARC, panel — all closed‑source                |
| Rootfs (SquashFS + UBI)      | Replaceable, but kernel modules are binary‑only                |
| DRM signing (PlayReady/Marlin)| Requires licensed signing keys; custom builds lose them        |

**Verdict**: Running a fully‑featured Android TV on this hardware
would require a complete board‑support package from Novatek, which
has not been released.  A **minimal custom Linux** (Buildroot /
Yocto) using the existing kernel and some binary blobs is more
plausible than an Android port.

---

## File inventory (original firmware)

| File                    | Size        | SHA‑256                                                              |
|-------------------------|-------------|----------------------------------------------------------------------|
| `kylo_usb_update.bin`   | 232 MiB     | `9259b4a17d5d19c99f1f44ea9d08c0cbec6b075c460a383a75bbe1065305e531` |
| `kylo_usb_update.scr`   | 5 KiB       | `ed8a1a02783a68503b675b8c20730d919844bd14767caae5abaadb7382fd23a5` |

---

## References

- Device tree (72 KiB, 1 500+ lines): extracted from FDT0 uImage.
- Kernel uImage headers: `Linux-4.9.118+`, ARM, gzip.
- Update script: `kylo_usb_update.scr` (full partition map).
- SPI flash data: string `NT72673`, boot timestamp `Jan 05 2021`.
- Board ID from bootloader: `4ccfBOOT`, PCB version `Rev.A`.

---
---

# MD30010 Medion Firmware — Static Analysis

> **Scope note.** Everything *above* this line describes the **original
> Horizon** firmware (`kylo_usb_update.bin` sha256 `9259b4a1…`, Kylo
> `V0.51.52.3`, SECOS built 2021‑09‑27, U‑Boot 2021). The section
> *below* documents the **separate MD30010 Medion full‑update image**
> (`MD30010_Firmware_Full_Update_DE.zip`) that was actually flashed onto
> the TV to downgrade it. The two images share the SoC and partition
> scheme but are different builds with different hashes and dates — do
> not conflate their values.

**Method:** static only — no flashing, no execution. The zip was
unpacked into an isolated scratch directory; sections were carved using
the authoritative offsets in `kylo_usb_update.scr` and identified with
`file`, `ubireader`, `unsquashfs`, plus REA's `inspect_byte_entropy` and
`inspect_devicetree`. Every region boundary is backed by **both** the
`.scr` burn commands **and** the on‑disk section headers.

## Container format

`MD30010_Firmware_Full_Update_DE.zip`
(sha256 `9ffb6afc61afe77e5794279652f9b470f88f8ab92608ee661c199ae69dd065fd`)
contains three members:

| Member | Size | Role |
|--------|------|------|
| `kylo_usb_update.bin` | 243,007,488 B | flashable image (sha256 `79c2475d2fb8c5ca0ff5fea097725df8fb22a17d9e05c790a0d1c1dbe6e212cf`) |
| `kylo_usb_update.scr` | 5,074 B | U‑Boot script — the burn recipe (sha256 `84b4633d070e5fc5c0e5564f37d64b350f5d5f61e9aa9bbb490bd0e53e276f32`) |
| `MD30010 Firmware Full Update DE.pdf` | 104,198 B | end‑user update instructions |

`kylo_usb_update.bin` is **not a single filesystem**. It is a Novatek
concatenation of **16 named sections**, each introduced by a 32‑byte
header:

```
AA AA 55 55 55 55 AA AA   <8-byte ASCII size>   <16-byte ASCII name\0…>
```

`file(1)` misreads the first header as "SoftQuad DESC"; the `AAAA5555…`
magic is the real marker. The payload of each section begins **+0x20**
after its header. The 16 headers were confirmed by scanning for the
magic and match the `nand write` / `sf write` commands in the `.scr`
exactly. Whole‑file Shannon entropy is **7.7566** (REA
`inspect_byte_entropy`) — consistent with mostly‑compressed content.

## Section map (MD30010)

`file_off` = offset inside `kylo_usb_update.bin` of the section payload
(header +0x20). `nand_off` = destination on the TV's NAND/SPI, read
directly from the `.scr`.

| # | Name | file_off | nand_off | len | Verified format |
|---|------|----------|----------|-----|-----------------|
| 1 | SPI | `0x00000020` | SPI `0x0` | `0x20000` | SPI config blob (`…000c0000 spi`) |
| 2 | XBOOT | `0x000c0020` | `0x0` | `0x35000` | 1st‑stage bootloader (raw, Novatek proprietary) |
| 3 | DDRCFG | `0x00100020` | `0x100000` | `0xb4000` | DRAM init blob |
| 4 | XBOOTDAT | `0x001c0020` | `0x2c0000` | `0x2000` | panel/board config |
| 5 | NPT | `0x001e0020` | `0x400000` | `0x1000` | NAND partition table |
| 6 | MISC | `0x00200020` | `0x4c0000` | `0x1000` | misc params |
| 7 | **SECOS** | `0x00220020` | `0x700000` | `0x15f000` | uImage "secos", **gzip**, load `0x8000`, built **2019‑09‑10** |
| 8 | **UBOOT** | `0x00380020` | `0x980000` | `0xc0000` | uImage **U‑Boot 2016.07‑g54205a2 for nt72**, Firmware/ARM, uncompressed, load `0x2800000`, **2019‑11‑07** |
| 9 | **FDT0** | `0x00440020` | `0xac0000` | `0x60000` | DTB v17, 72,627 B, load `0x4800000`, **2020‑01‑20** |
| 10 | **FDT1** | `0x004c0020` | `0xc00000` | `0x60000` | **byte‑identical to FDT0** (fallback) |
| 11 | **KER0** | `0x00540020` | `0xd40000` | `0x4c9000` | uImage **Linux‑4.9.118+**, gzip, load/ep `0x2808000`, **2020‑04‑01** |
| 12 | **KER1** | `0x00a20020` | `0x1440000` | `0x84c000` | uImage Linux‑4.9.118+, gzip, load/ep `0x2808000`, **2019‑06‑26** (fallback/recovery kernel) |
| 13 | **FS0** | `0x01280020` | `0x2040000` | `0xb980000` | **UBI image v1** — 4 volumes (see below) |
| 14 | APDAT0 | `0x0cc20020` | `0xe340000` | `0x3c0000` | UBI image — volume `apdat0` → `/conf` |
| 15 | BUFFER | `0x0d000020` | `0xed40000` | `0x1740000` | UBI image — volume `buffer` → `/buffer` |
| 16 | LOGO | `0x0e760020` | `0x1fd40000` | `0x45000` | JPEG (Exif, Vestel) boot logo |

uImage header magic for sections 7–12 is `0x27051956` (U‑Boot legacy),
all `arch = ARM (2)`. The DTB reports `model = "Novatek NT72673"`,
`compatible = "nvt,ca53"`, version 17, 492 nodes, 0 memory
reservations (REA `inspect_devicetree`).

**Kernel boot arguments** (verbatim from FDT0 `chosen/bootargs`):

```
console=ttyS0,115200 no_console_suspend earlyprintk rootflags=nvt_security
vmalloc=504M maxcpus=4 ubi.mtd=12 ubi.block=0,0 root=/dev/ubiblock0_0
rootfstype=squashfs ro quiet init=/init rootwait
```

→ UART console @115200, 4 CPUs enabled, rootfs is **SquashFS mounted
read‑only over a UBI block device**, `init=/init`, `nvt_security`
integrity flag.

## Filesystems

### FS0 → UBI (4 volumes)

| Volume | Mount | Format | Contents | SquashFS build |
|--------|-------|--------|----------|----------------|
| `fs0` | `/` (rootfs) | SquashFS v4 / zlib, 556 inodes, 5.4 MB | BusyBox userland | 2020‑07‑07 |
| `ap0` | `/vendor` (ro) | SquashFS v4 / zlib, 7,429 inodes, 147 MB | the TV application stack | 2020‑07‑07 |
| `ap1` | `/vendor2` (ro) | SquashFS v4 / zlib, 298 inodes, 26 MB | language profile, kernel modules, HTML apps | 2020‑08‑04 |
| `nvt_sign` | — | 253,952 B, non‑filesystem | `nvt_security` signature material | — |

- **APDAT0** → UBI volume `apdat0`, mounted writable as **`/conf`** —
  the PQ / audio / panel tuning store (`ptf.ptf`, `PCF.pcf`, `PQF.bin`,
  `AQ.bin`, `mb230_hwprofile.bin`, `mb230_swprofile.bin`,
  `service_menu.txt`, sqlite DBs). This is the volume the service‑menu
  USB dump exposes.
- **BUFFER** → UBI volume `buffer`, mounted as **`/buffer`** — Cobalt
  (YouTube) bundle, OpApp, downloaded images.

## Boot & init chain

```
XBOOT → DDRCFG → SECOS (secure OS) → U-Boot 2016.07 → FDT + kernel 4.9.118
      → SquashFS rootfs (ubiblock0_0) → /init (BusyBox)
```

| Stage | Evidence | Behaviour |
|-------|----------|-----------|
| `/init` | symlink → `bin/busybox` | BusyBox init |
| `/etc/inittab` | `::sysinit:/etc/rc.local` then `::respawn:/bin/cttyhack /bin/login` | **a commented‑out line directly above would respawn a root `/bin/sh` on the console instead of `login`** — relevant to the root‑shell goal |
| `/etc/rc.local` | carved from `fs0` | mounts proc/sys/tmpfs; sets up **zram lz4 swap (350 MB)**; shows bootlogo; `ubiattach` + mount `ap0→/vendor`, `ap1→/vendor2` (ro squashfs); `ifplugd` on eth0; then runs `startup.sh` |
| `/usr/script/startup.sh` | carved | `cd /vendor; ./run.sh`, else falls back to `/media/sda[1]/board/run.sh` (**"run AP from USB"** path — an unsigned USB stick with a `board/` dir can supply the app) |
| `/vendor/run.sh` | carved from `ap0` | real app launcher: binds firmware, inserts kernel modules via `install_fpga.sh`, mounts `/conf`, then launches `com.nvt.appmgr`, or `com.nvt.idtv/aurora.elf` via `run_aurora.sh`, or a standalone browser |

`/etc/passwd` defines root plus sandboxed per‑app users (`appmgr`,
`idtv`, `Netflix`, `Youtube`, `Amazon`, `Opera`, `dial`, `miracast`,
`ntts`, `priv`) — most with `/bin/false` shells. rootfs build tag
`/etc/.version` = `SHA1(b2c9ec9) | 2019-10-21`.

## Application "services"

All under `/vendor/com.nvt.*`, ARM 32‑bit ELF (`EABI5`), dynamically
linked:

| Dir | Role |
|-----|------|
| `com.nvt.idtv` (`aurora.elf`) | main TV application |
| `com.nvt.appmgr` | application manager |
| `com.nvt.cobalt` | Chromium‑based Cobalt (YouTube) |
| `com.nvt.nflx` | Netflix |
| `com.nvt.amazon` | Prime Video / Alexa |
| `com.nvt.dial` | DIAL (second‑screen launch) |
| `com.nvt.samba` | SMB/CIFS |
| `com.nvt.privserver` | privileged helper |
| `com.nvt.xpca` | Novatek XPCA |

## Security‑relevant findings

### 1. Built‑in gdbserver / CIFS remote‑run backdoor

`/vendor/run_aurora.sh` contains a developer remote‑debug path that runs
the **main TV binary from a network share under gdbserver**, gated only
by the presence of a file in the *writable* `/conf` volume — no UART and
no reflash required. Mechanism:

- If `/conf/remote.txt` exists, its single line is parsed as
  `isgdb:ip:username:password`.
- The script brings `eth0` up with a **hardcoded default MAC
  `D4:E2:CC:EC:45:E9`**, runs `udhcpc`, `insmod`s `cifs.ko`, and mounts
  `//<ip>/mb230cifs` at `/conf/remotelf`.
- If `isgdb == 1` and `remotelf/aurora.elf` is present, it launches that
  **operator‑supplied `aurora.elf` under gdbserver**.

Because `/conf` (= `apdat0`) is exactly the volume the service‑menu USB
"Download" operation can write, this is a realistic path to execute a
modified main application **without touching secure boot, SECOS, or the
signed `nvt_sign` volume**. The hardcoded MAC and the `mb230cifs` share
name are the concrete hooks.

### 2. Dormant network daemons

BusyBox in `/usr/sbin` ships `telnetd`, `ftpd`, `httpd`, `inetd`, and
`tftpd` applets, **but no init script starts them**. They would have to
be launched manually (e.g. from the `/conf` or USB `startup` / `run`
paths above).

### 3. USB auto‑run

`startup.sh` and `run.sh` will execute `board/run.sh` from an inserted
USB stick (`/media/sda[1]/board/`) when `/vendor/run.sh` is run from
USB — an intended factory path, usable to run custom userland code.

## DRM / key material burned by the `.scr`

The update script conditionally burns **PlayReady** keys
(`update_playready_key`, SPI region `0x20000`) and **Marlin**
personalisation keys (`update_marlin_key`, SPI `0x27C00`). These and the
`nvt_sign` volume are the integrity/DRM anchors; they were **not read or
extracted** during analysis.

## Not extracted / unknowns (MD30010)

- **XBOOT, DDRCFG, SECOS** — carved and identified, not decompiled
  (proprietary Novatek blobs).
- **`nvt_sign` (253 KB)** — the `nvt_security` signature scheme is not
  derivable from static bytes alone.
- Credential / key material encountered during extraction
  (`/etc/shadow`, `MB230_service.key`, `aws_iot_certs`,
  PlayReady/Marlin key regions) was **deliberately not inspected**.
- REA's `inspect_firmware_regions` / `extract_firmware` require an
  absolute `REA_BINWALK_COMMAND` / Unblob path, which was not configured
  in this environment; carving was done from the authoritative `.scr`
  offsets and cross‑checked with REA's entropy and DTB parsers and with
  `ubireader` / `unsquashfs`.