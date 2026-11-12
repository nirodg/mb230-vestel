# U-Boot USB diagnostics channel (read-only)

A **confirmed, non-destructive** way to run U-Boot commands on the MB230
and pull data back — USB only, no serial, no opening the TV, **zero
writes to the TV's flash**.

## Why this works
U-Boot (`2016.07`, NT72671) sources a **plain-text** `kylo_usb_update.scr`
from the FAT32 stick **root** when the TV powers on **holding `OK`**. The
script is **not** signature-checked (only a trailing `%` marker is
required), so a custom script runs. `fatwrite` is compiled in, so the
script can write result files **back to the stick**. Confirmed on
hardware 2026-11-12. Details + evidence: `../../ARCHITECTURE.md`.

**Scope is read-only by design.** The boot chain verifies images
(`verify=y`, vhash, `nvt_sign`, `bootsecure`), so this channel **cannot
boot a custom OS** — it is a flash-dump / diagnostics tool. The OpenTV
userland runs via the *separate* Linux "Run AP from USB" path
(`../board/run.sh`), not here. See `../../OPENTV.md`.

## Use `opentv_probe.scr`
Dumps, all read-only: a run marker, the live U-Boot `env`, and the
`xbootdat` / `npt` / `misc` NAND regions + SPI `0..0x20000`.

```
cp stage1/uboot/opentv_probe.scr   <FAT32 stick>/kylo_usb_update.scr
#  (do NOT also place kylo_usb_update.bin — that arms a full reflash)
```
1. Insert stick, TV unplugged.
2. Plug in **holding `OK`** → `USB AUTO UPDATE!!`.
3. Wait a few seconds, power off, pull the stick.
4. Read `opentv_probe_ran.bin` (marker `NVOK`), `opentv_uboot_env.txt`,
   and `dump_*.bin` on a PC.

## Safety contract (keep it)
This script contains **no** `nand/sf erase`, **no** `nand/sf write`, no
`nwriteloader`/`trimffs`, no `saveenv`. It only `nand read` / `sf read`
into RAM and `fatwrite` to the USB stick. If you edit it, keep it that
way: any `nand erase`/`write` here can **permanently brick** the TV
(the stock update `.scr` erases XBOOT/U-Boot/SECOS first).
