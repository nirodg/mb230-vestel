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
Dumps, all read-only: a run marker, the live U-Boot `env`, plus
per-investigation `nand read`/`sf read` targets. The dump list evolves;
check the script header for the current round.
- **Round 1 (done):** `xbootdat[0:8K]` (= panel config, not cmdline),
  `npt`, `misc` (0x0e filler), SPI `0..0x20000` (board id + MAC/keys).
- **Round 2 (done):** full `xbootdat` (recovery cmdline), `fdt0`
  (device tree), `apdat0` (= writable `/conf`).
- **Round 3 (done):** SPI again + `apdat0` 3.75 MiB prefix — first
  evidence of the vendor scatter-attached BE-header UBI.
- **Round 4 (done):** SPI full `0..0x40000` (MAC block `@0x23000`
  confirmed, ASCII, matches `/conf/mac.txt`) + full 10 MiB `apdat0`
  ⇒ conf write verified live, `ntkethmac.ko` root cause established.
- **Round 5 (done):** fs0 head 2 MiB read `@0x1fc0000` — turned out
  2 PEBs before fs0's true start (`0x2040000`, per the stock `.scr`'s
  `nand write.trimffs … 0x2040000`), but the header-scan recovered the
  full volume table anyway: `ap0` = **dynamic, 607 PEBs** ⇒ Track-C
  is a go.
- **Round 6 (done, not a probe):** Track-C ap0 WRITE executed via
  `ap0_write.scr` — CRC read-back verified (`NVOK`). Findings:
  driver fix works, TV now reaches SMB; new blocker = missing kernel
  crypto for NTLMSSP (see ARCHITECTURE.md round 6 + server/README.md
  fix plan for the v2 HTTP patch).

Findings are recorded in `../../ARCHITECTURE.md`. Device secrets found in
these dumps (MAC, key material) are **never** committed.

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

## Track-B (executed 2026-11-13 — SUCCESS)
The `/conf` rewrite was performed on hardware and is confirmed live:
- `conf_new.ubifs` (current `/conf` + `remote.txt`, m=4096 e=253952
  c=31 x=lzo) written via `fatload` + `ubi part apdat0` + `ubi write`.
- Round-4 full `apdat0` dump (10 MiB, all 40 PEBs) proves the TV
  booted Linux with it repeatedly and its own UBI garbage-collected
  the volume (erase counters 1–13, scatter-attached layout).
  `remote.txt` survives.
- `make_conf_image.sh` + `conf_write.scr.TEMPLATE` remain as the
  reusable rewrite/restore tooling for `/conf`.
- Restore reference: the round-4 live dump (`dump_apdat0.bin` from
  probe v4) and the factory `apdat0_factory.ubi` (carved from MD30010).

## Track-C (EXECUTED 2026-11-13 — write verified; v2 patch pending)
Root cause of the remote.txt black-screen loop (see
`ARCHITECTURE.md` § "Wired network bring-up", round 4): in the debug
path `ntkethmac.ko` is never loaded, so `eth0` does not exist and
`run_aurora.sh` fails before DHCP. There is no network-free `/conf`
exec hook, so the fix is one line in the read-only OS volume:

```
+   insmod /vendor/modules/ntkethmac.ko     # before the ifconfig block
```

**v1 EXECUTED and verified on hardware (2026-11-13):**
- `ap0_write.scr` ran the full pipeline: `fatload` 154,017,792 B →
  `ubi part fs0` → `ubi write 0x3300000 ap0 0x92e2000` → read-back →
  **CRC32 verified** (`bab70164`); marker `ap0_write_ok.bin` = `NVOK`.
- Result on first normal boot: eth0 exists, DHCP lease, ARP, TCP/445
  to the PC, SMB1 + SPNEGO negotiate — then the TV aborts NTLMSSP
  auth because the kernel lacks `hmac(md5)`/`md4`/`des`/`arc4`
  (round 6, ARCHITECTURE.md). Loop persists at a LATER stage now.
- `ap0_restore.scr` + `ap0_factory.squashfs` remain on the stick =
  one-boot return to stock ap0.

**v2 patch (BUILT & STAGED 2026-11-13, awaiting go):** replaces the
CIFS mount+exec block in `run_aurora.sh` with: `/conf/aurora.elf`
local exec (network-free, wins if present) → else
`timeout 20 wget -O /conf/remotelf/aurora.elf http://$ip_addr:8123/aurora.elf`
+ exec (plain HTTP, no kernel crypto; `$ip_addr` still from
remote.txt) → else the original CIFS block unchanged (harmless).
Built as `ap0_patched_v2.squashfs` on top of the v1 tree:
154,017,792 B (`0x92E2000`, crc32 `0x11A83E1B`), superblock verified
(compr 1, block_log 18, flags 0xc0, no_ids 1), round-trip diff clean.
Armed script: `ap0_write_v2.scr` (same pipeline + read-back CRC
verify, marker `ap0_write_v2_ok.bin`). Port 8123 chosen because 8000
is occupied on the PC. Stick state: `kylo_usb_update.scr` = read-only
probe (safe default), v2 script parked under its own name.

Facts (probe v5 + MD30010 carve, all verified):
- `fs0` mtd @ **`0x2040000`**, 195 MiB (780 PEBs); standard mainline
  UBI; live volume table: `fs0`=23 PEBs, **`ap0`=607 PEBs dynamic**,
  `ap1`=111 PEBs (no `nvt_sign` in the live table).
- `ap0` = raw SquashFS 4.0 (zlib, 256 KiB blocks, all-root),
  154,015,107 B of filesystem + 0xff padding to the full 607-LEB
  capacity (154,148,864 B) in the factory image.
- `ap0_patched.squashfs` (v1) = 154,017,792 B (`0x92E2000`,
  crc32 `0xBAB70164`) — exactly 607 LEBs.
- `ap0_factory.squashfs` = 154,148,864 B (`0x9302000`,
  crc32 `0x98EC4C01`) — the exact factory volume image = restore
  reference (fs0 is mounted read-only, so factory = live).

Safety shape (unchanged): the write touches only the `ap0` volume's
data LEBs (dynamic-volume update); layout/vtbl/`fs0`/`ap1`/signed/
boot data untouched. Interrupted write ⇒ volume marked "updating" ⇒
black screen, recoverable by re-running write or restore via the
OK-boot channel. NAND wear: one erase cycle per block — negligible.
