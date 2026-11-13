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

## USB U‑Boot script channel (CONFIRMED on hardware, 2026‑11‑12)

U‑Boot (`U-Boot 2016.07-g54205a2 for nt72`, internal link base
`0x2836200` recovered from the command/partition name pointers) runs a
**plain‑text** `kylo_usb_update.scr` from the FAT32 stick **root** when
the TV is powered on **holding `OK`** on the remote (banner
`USB AUTO UPDATE!!`). The stock `.scr` is the full‑reflash burn recipe
(`nand erase.chip` + per‑section `nand/sf write`); it is **destructive
and irreversible** and overwrites XBOOT/U‑Boot/SECOS first.

**Key finding — the script itself is NOT signature‑checked.** The loader
(`nvtsource` = "run script from memory", `nvt_script_update` = "upgrade
firmware according to auto script") sources the text directly; the only
validation is the trailing `%` end marker ("incorrect script format!
place %% at the end"). `sha256_chk` is a *separate* general command the
script may call, not an automatic gate. A **custom** `.scr` therefore
executes. This was verified: a non‑destructive probe (`mw` + `env export
-t` + `fatwrite usb 0:auto`) wrote marker + env files back to the stick,
FAT‑dated 1980‑01‑01 (U‑Boot has no RTC ⇒ written **pre‑Linux**).

**But unsigned images still cannot boot.** The chain verifies at
boot/read time — `nvt_calc_vhash`, `nvt_nand_update_vhash`, `bootsecure`,
`nvt_sign`, env `verify=y`. So the channel is a **read‑only diagnostics /
RE tool**, not a way to boot a custom OS: `fatwrite` + `nand read` /
`sf read` can dump any partition to USB with **zero flash writes**.

Live U‑Boot environment (via `env export`, the compiled‑in default):

| var | value |
|-----|-------|
| `board` / `board_name` | `nt72671b_a32_n33006_nand` |
| `soc` | `nt72671_a32` |  | `cpu` | `armv8` | `cpus` | `4` |
| `bootcmd` | `reboot` (default — real boot uses the recovery cmdline in `xbootdat`; see `xdump/xsave rcvcmd`) |
| `bootdelay` | `60` |  | `verify` | `y` (secure boot on) |
| `baudrate` | `115200` (UART, if ever wired) |
| `kernel_loadaddr` | `0x27FFFC0` |
| `mtdparts` | matches the NAND table below |

Repo tool: `stage1/uboot/opentv_probe.scr` (deploy as
`kylo_usb_update.scr`) — a non‑destructive dump script (marker, env, +
per‑investigation `nand read`/`sf read` → `fatwrite` dumps).

**Dump results (2026‑11‑12, read‑only via this channel):**
- `xbootdat` first 8 KiB = **panel config** (`PIDX`/`PANL`, interface
  `VX1_Direct`), *not* the boot cmdline — the saved recovery cmdline is
  deeper in the 1.25 MiB partition (next dump).
- `npt` = the on‑flash NAND partition table; names/layout match the
  `.scr` map below (record = 16‑byte name + LE u32 offset + LE u32 size).
- SPI `0..0x20000` = XBOOT + board/config block: ids `4ca4BOOT`,
  `NT72673` / `Novatek_NT72682`, XBOOT build `Nov 07 2019`, config
  `Jun 17 2020`, `Rev.A`, `v001`. **Also holds a `MAC` field and key
  material — device secrets, deliberately not reproduced here.**
- `misc` first 4 KiB = `0x0e` filler (no useful content).

**Round 2 (2026‑11‑12):**
- `fdt0` `/chosen` holds the **live kernel cmdline**:
  `console=ttyS0,115200 … rootflags=nvt_security vmalloc=504M maxcpus=4
  ubi.mtd=12 ubi.block=0,0 root=/dev/ubiblock0_0 rootfstype=squashfs ro
  quiet init=/init rootwait`. It is stored in the **signed `fdt0`**
  partition ⇒ cannot be changed (e.g. `init=`) without re‑signing;
  confirms the secure‑boot wall from live flash.
- Full `xbootdat` (1.25 MiB) = panel config only; **no** saved recovery
  cmdline on this unit (the `xsave rcvcmd` slot is empty here).
- `apdat0` = **`/conf`**, a writable UBI/UBIFS volume (extracted with
  `ubireader`, 60 files): the TV profiles (`mb230_hwprofile.bin`,
  `mb230_swprofile.bin`, `ptf.ptf`, `PCF.pcf`, `PQF.bin`, `AQ.bin`),
  config/XML, sqlite DBs, and **shell scripts the firmware executes on
  Wi‑Fi/P2P events** (`wifi/mtk_wifi_connectap_action.sh`,
  `wifi/p2papp_connected.sh`, `wifi/udhcpc-p2p.script`).
  `disable_sh_command.txt` is empty; no `remote.txt`/`aurora`/`gdb`/`cifs`
  present on this unit. Secrets in `/conf` (`mac.txt`, service‑menu
  product code) are **not reproduced here**.

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

## Rounds 7–10 (2026-11-13): the ap0 revert + update machinery

Facts carved from the firmware (MD30010 package + live dumps); live-TV
observations via the U-Boot probe channel (`stage1/uboot/`).

- The `fs0` mtd partition is one UBI with **4 volumes** (package image,
  cross-checked against the live volume table): `ap0` (607 LEBs,
  SquashFS app volume), `ap1` (109 LEBs, SquashFS **overlay**:
  `dynamic_ui`, AudioDSP `firmware/`, `html_applications`,
  `modules/ntkdriver_dovi.ko`, `oss` — no flasher), `fs0` (23 LEBs,
  rootfs UBIFS), `nvt_sign` (1 LEB, high-entropy signature blob).
  Boot mounts: `ap0`→`/vendor` (ro), `ap1`→`/vendor2` (ro, `rc.local`
  line 83), `apdat0`→`/conf` (rw).
- `startup.sh` runs `/oad/oadLoader` when present — but `/oad` ships
  empty (rootfs and ap1 both), so that OTA path is dead on this unit.
- The **software-update machinery lives in ap0**: `com.nvt.idtv/
  aurora.elf` (28.7 MB app) strings include `oadWriteFlashAndReboot`,
  `rootfs_burn.img`, `board_burn.img`, "Start the web search for
  forced software update and burn flash if exists", `echo
  nvt_trigger_update > /tmp/trigger_reboot`, `INCSWUPDATECOUNTERS
  0-USB 1-HTTP 2-SIDE_LOAD_USB`, `/conf/fto.bin`, and `/buffer/
  conf_backup/*` maintenance. `nvt_trigger_update` (ap0 root) is a
  383 KB **static ARM ELF flasher tool** (BuildID `32a8f01f…`),
  referenced only by aurora.elf. `/conf/fto.bin` +
  `/conf/ftpUpdateVersionFile.txt` record the update state
  (`V.0.51.19.0,V.0.51.52.5` after the documented Medion downgrade —
  the TV sees a newer version available).
- `/conf` maintenance: `mtdmount.sh mount_apdat()` reformats `apdat0`
  only after 3 failed mounts and then restores `/buffer/conf_backup/*`.
  The live `/conf` image_seq (`0x67025800`) equals the factory image's
  ⇒ **never reformatted**. The `buffer` volume (1037 PEBs reserved)
  is provably never written (EC-stamped, VID-erased head, no UBIFS
  magic) — it is NOT an ap0 backup store on this unit.
- **Observed live:** during the v2.1 loop session (10:45–11:40, nine
  DHCP+mount cycles ~33 s apart, the stock app never running) the TV's
  `ap0` volume returned to byte-identical factory content (probe v7
  live prefix CRC `0x18def0da` == factory). xbootdat unchanged since
  round 1 (no boot counters), buffer empty, rootfs 5.8 MB, ap1
  unchanged ⇒ no local source holds 154 MB of factory ap0 bytes ⇒ the
  only remaining writer is the TV's own update machinery downloading
  over the internet. Note: `ap0` is byte-identical across SW versions
  (app updates ride the `ap1` overlay), so an applied OTA would NOT
  change the ap0 fingerprint — probe v9 fingerprints `ap1`/`nvt_sign`/
  `fs0`/`ker1` against the package to detect any OTA write.
- Mitigation shipped in payload v3.1: re-delete the default route
  every 30 s (`route del default`; busybox has no `ip` applet) so the
  OTA download path cannot run while telnet/LAN stay reachable, plus
  a 30 s ap0/nvt_sign fingerprint trap that dumps process state to
  `/conf/opentv_revert.log` on any change.

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

## Wired network bring‑up (carved from fs0/ap0/fdt0, 2026‑11‑13)

Evidence trail for how this firmware gets an IP — cited from the MD30010
image (`fs0`/`ap0` SquashFS volumes and `fdt0`, carved 2026‑11‑13):

- **DTS `fdt0`:** `ethernet@fd160000` — `compatible = "nvt,synopsys-mac"`
  (Synopsys DesignWare MAC), no PHY/MDIO node; the MAC driver ships as
  the module `ap0/modules/ntkethmac.ko`.
- **`fs0/etc/rc.local` (`setup_network`):** starts `ifplugd -i eth0
  -t 1 -d 0`. On link change, `fs0/etc/ifplugd/ifplugd.action` writes
  `1`/`0` into the FIFO `/tmp/nvtpipe/linkstat`.
- **`ap0/run.sh` → `gstreamer.sh` → `script_network.sh &`**
  (backgrounded): `insmod /vendor/modules/ntkethmac.ko`, `ifconfig lo
  up`, and copies the WiFi/P2P helper scripts into `$WIFI_CONF_DIR`
  (`/mtd_apdat/wifi` — MTK `mt7662u_sta.ko`).
- **`com.nvt.idtv/aurora.elf`** consumes the `linkstat` FIFO and runs
  DHCP itself: `udhcpc -q --release -T 2 -n -t 2 -A 0 -i %s -h "%s-TV"`
  — **2 tries × 2 s timeout, then it gives up** (no infinite retry in
  the normal path). It sets the MAC (`ifconfig eth0 down hw ether %s`,
  defaults seen in strings: `00:09:df:88:34:26`), skips eth0 when WiFi
  is already connected, and kills stale clients first
  (`killall -9 udhcpc`, `pkill -9 -f 'udhcpc -i %s'`).
- **Contrast:** the debug path `ap0/run_aurora.sh` (armed via
  `/conf/remote.txt`) runs a **plain `udhcpc -s /etc/udhcpc/default.script
  eth0`** — no `-n`/`-t`/`-T` ⇒ **blocks forever without a lease** —
  after forcing the default MAC `D4:E2:CC:EC:45:E9`. A lease failure
  therefore wedges the idtv program ⇒ stock watchdog reboots ⇒ the
  observed black‑screen reboot loop; the stock (aurora) path cannot
  wedge this way because its `udhcpc` gives up after ~4 s.

**Round 4 (2026‑11‑13, live dumps) — root cause of the remote.txt
black‑screen loop.** Probe v4 read SPI `0..0x40000` (adds the MAC/config
block at SPI `0x23000`, which holds the eth0 MAC as ASCII — matches
`/conf/mac.txt`; value deliberately not reproduced) and the full 10 MiB
`apdat0` (all 40 PEBs; NPT confirms `0xE340000`, 10 MiB). Findings:

- **The Track‑B `conf` write succeeded and is live.** The live `apdat0`
  UBI has since been organically rewritten by the TV itself (EC
  counters 1–13, layout copies at PEB30/PEB10 — ordinary wear‑leveled
  placement, standard UBI) — proof the TV booted Linux with our image
  and its UBI garbage‑collected it. `remote.txt` survived with our
  content.
- **Our payload never ran:** no `/conf/opentv_aurora.log` in the live
  FS, and smbd on the PC never saw a connection from the TV.
- **Root cause (static, confirmed by absence of any TV frame on the
  wire in two captures):** in the debug path appmgr launches
  `run_aurora.sh` instead of the stock app, and **`ntkethmac.ko` is only
  ever `insmod`ed by `script_network.sh`, whose only caller is the stock
  `aurora.elf`** (string `./script_network.sh` inside the binary).
  `run.sh` itself never calls `script_network.sh` — `gstreamer.sh`
  (its only shell reference) is in turn referenced by no script or ini.
  So in the remote.txt path `eth0` does not exist: `ifconfig` ×3 fail,
  `udhcpc` exits immediately, `mount.cifs` fails, `$REMOTELF/aurora.elf`
  is missing, the script exits, the FG app is gone ⇒ reset ⇒ loop.
- **No alternative `/conf` exec hook exists in this firmware:**
  `/conf/run_with_dwelf` is dead (`data/nvt.app.dwelf.ini` is absent
  from the read‑only volume), `run_nfs.sh` is absent so the `telnetd`
  block never runs, and `/conf/standalone_browser.bin` only toggles
  `RUN_BROWSER_STANDALONE` env exports (no app in any ini points at a
  `/conf` binary). Any fix that makes the remote.txt path work must
  therefore get `ntkethmac.ko` loaded — i.e. patch `ap0` (Track‑C).

**Track‑C target volume (carved from MD30010 + live fs0 vtbl,
2026‑11‑13).** `fs0` (mtd, **`0x2040000`**, 195 MiB = 780 PEBs — per
both the live `mtdparts` arithmetic *and* the stock update script's
`nand write.trimffs 0x4580020 0x2040000 0xb980000`; note the earlier
`0x1FC0000` figure in round‑5 notes was 2 PEBs early — ker1's tail;
the probe's header-scan made the parse position‑independent) is one
UBI stream. **Live volume table** (probe v5, layout at fs0 PEB0/1,
standard 172‑byte records, CRCs valid):

| volume | rsvd_pebs | type | capacity (LEB 253,952) |
|---|---|---|---|
| `fs0` | 23 | dynamic | ~5.8 MB |
| `ap0` | 607 | **dynamic** | 154,148,864 B |
| `ap1` | 111 | dynamic | ~28 MB |

(`nvt_sign` exists in the update image but is **not** in the live
table — 3 volumes only.) The headers are **standard mainline UBI**
(multi‑byte EC/VID fields are big‑endian *per spec*; the earlier
"vendor BE variant / scattered layout" reading was a misparse —
round‑3's `ubireader` failure was only the truncated 15‑PEB window
missing the second layout copy, and "scattered" placement is ordinary
wear‑leveling). The `ap0` volume contains a **raw SquashFS 4.0 image**
(zlib, 256 KiB blocks, all‑root, 154,015,107 bytes + 0xff padding to
the full 607‑LEB capacity, build stamp `Jul 7 2020`).

**Go condition met:** `ap0` is dynamic with 607 LEBs; the patched
rebuild is 154,017,792 B (`0x92E2000`, crc32 `0xBAB70164`) = exactly
607 LEBs — fits. Written back with the proven Track‑B channel
(`fatload` → `ubi part fs0` → `ubi write … ap0`). Patch: one added
`insmod /vendor/modules/ntkethmac.ko` in `run_aurora.sh` before the
`ifconfig eth0` block; see `stage1/uboot/README.md` for state.

**Round 6 (2026‑11‑13 ~03:50) — Track‑C EXECUTED and verified; new
failure point found (SMB auth needs kernel crypto the TV lacks).**

- **The ap0 write succeeded on hardware:** marker `ap0_write_ok.bin`
  = `NVOK`; the script read the whole 607‑LEB volume back and the
  CRC32 matched `0xBAB70164`. `stage1/uboot/ap0_write.scr` /
  `ap0_restore.scr` are the reusable write/restore scripts.
- **The driver patch works.** First normal boot after the patch
  (capture `/tmp/opencode/tv_boot5.pcap`, PC on WiFi = 192.168.0.100):
  the forced MAC **`D4:E2:CC:EC:45:E9` appeared on the wire** — eth0
  now exists in the remote.txt path. DHCP lease obtained
  (192.168.0.136), ARP for 192.168.0.100 answered by the PC, and a
  **TCP session to the PC's :445 was established**.
- **SMB got further than ever and died mid‑auth:** smbd negotiated
  SMB1 ("Selected protocol NT LM 0.12"), SPNEGO session setup started,
  client identified itself as `NativeOS=[Linux version 4.9.118+]
  NativeLanMan=[CIFS VFS Client for Linux]`, received the NTLMSSP
  challenge (neg flags `0xe0080225`) — and then the TV **closed the
  connection (FIN ~0.5 s after SYN) without ever sending NTLMSSP
  AUTHENTICATE** (smbd: "Server Exit (failed to receive smb
  request)"). The watchdog loop persists (logo → black → off → ~30 s
  cycle) because `mount` fails → `run_aurora.sh` exits → FG app gone.
- **Root cause #2 (client‑side kernel crypto missing):** the TV's
  `cifs.ko` (v2.09, vermagic `4.9.118+ SMP preempt mod_unload ARMv7`,
  no module deps) requests `hmac(md5)`, `ecb(arc4)`, `arc4`, `md5`,
  `des` from the kernel crypto API (module strings: "could not
  allocate crypto hmacmd5" …). The **boot kernel `ker1` has none of
  them built in** — extracted from the update image (uImage hdr
  `@0xA20020`, name `Linux-4.9.118+`, gzip payload `@0xA20060`,
  14,354,072 B decompressed; no `IKCFG_ST` embedded config):
  `hmac` = 0 hits, `arc4` = 0, `ecb(arc4)` = 0, standalone `md4`/`des`
  = 0 — only `md5`/`aes`/`sha1`/`sha256` are registered. **No crypto
  modules ship anywhere** (`ap0/modules` = net/usb/bt/nfs/mali only,
  `ap1` contains zero `.ko` files, `fs0/lib/modules` = ntk‑* display/
  tuner/kteeclient only). NTLMv2 needs `hmac(md5)`; NTLMv1 needs
  `md4`+`des` — neither can ever load, so session setup aborts
  exactly at the challenge. (The recovery kernel `ker0` is equally
  bare.)
- **A server‑side dodge is impossible:** every Samba auth flavor
  requires client-side crypto (plaintext passwords were removed from
  Samba long ago).
- **Fix path (ap0 patch v2, built 2026‑11‑13):** replace the CIFS mount
  + exec in `run_aurora.sh` with a plain‑HTTP fetch — **busybox `wget`
  and `timeout` are confirmed present** in the TV's rootfs
  (`fs0/usr/bin/wget` → busybox): `/conf/aurora.elf` local exec if
  present, else `timeout 20 wget -O /conf/remotelf/aurora.elf
  http://$ip_addr:8123/aurora.elf` → exec — plain HTTP needs no kernel
  crypto. PC side: `python3 -m http.server 8123 -d /srv/mb230cifs`
  (running; port 8000 was already occupied on the PC) + ufw allow.
  v2 image: 154,017,792 B, crc32 `0x11A83E1B`.
- Environment notes: the experiment now runs with the **PC on WiFi**
  (`wlp5s0` = 192.168.0.100 — coincidentally the same IP `remote.txt`
  points at; a router DHCP reservation for the PC's WiFi MAC is
  recommended so it stays `.100`); ufw is active but :445 was confirmed
  reachable; the TV itself must stay on **ethernet** (the remote.txt
  path is eth0‑only).

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