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