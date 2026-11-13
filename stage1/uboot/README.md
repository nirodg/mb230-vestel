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

**v2.1 (EXECUTED 2026-11-13):** absolute paths (`/usr/bin/wget`,
`/usr/bin/timeout`) + a `/conf/opentv_boot.log` per-boot log; armed as
`ap0_write_v21.scr`, marker `ap0_write_v21_ok.bin` = `NVOK` (write +
CRC read-back verified live). Result (rounds 7–8): the TV still never
reached :8123 (pcaps + HTTP log agree — only internet scanners hit
the PC); the script looped ~33 s per cycle (DHCP + SMB per cycle,
`opentv_boot.log` created 0 B) — and **ap0 came back FACTORY**:

**Probe v7 (lesson + fingerprint):** raw `nand read` FAILS after
`ubi part fs0` — do raw reads first, attach after. Live ap0
prefix-256KiB CRC `0x18def0da` == factory ⇒ the v1 ap0 write was
reverted to byte-identical factory content.

**Probe v8 (read-only):** `xbootdat` byte-identical to round 1
(0 bytes differ ⇒ no boot counters changed); `buffer` head 2 MiB =
formatted, never written (EC-stamped PEBs, VID erased, no UBIFS/
hsqs/conf_backup strings); fresh `/conf` differs from round 4 only
by `opentv_boot.log` (0 B — proof the v2.1 script ran); `/conf`
image_seq `0x67025800` == the factory `apdat0` image_seq ⇒ **`/conf`
was never reformatted** (mount_apdat's recovery path never fired).

**Round 9 (PC-side, no TV cycle):** the full `fs0` partition image
from the Medion package parses into 4 volumes: `ap0` 607 LEBs,
`ap1` 109 LEBs (squashfs overlay: dynamic_ui / AudioDSP firmware /
html_applications / ntkdriver_dovi.ko / oss — no flasher), `fs0`
23 LEBs (rootfs; the earlier carve was already complete), `nvt_sign`
1 LEB. Boot map: ap0→`/vendor`, ap1→`/vendor2` (ro), apdat0→`/conf`
(rw); `startup.sh` runs `/oad/oadLoader`, but `/oad` ships empty
(dead path on this unit). The update machinery lives in ap0:
`aurora.elf` strings (`oadWriteFlashAndReboot`, `rootfs_burn.img`,
`board_burn.img`, "web search for forced software update and burn
flash", `INCSWUPDATECOUNTERS`, `/conf/fto.bin`) + `nvt_trigger_update`
= a 383 KB static ARM ELF flasher tool referenced only by aurora.elf.
Revert-source candidates eliminated: xbootdat, buffer, fs0 rootfs,
ap1, oadLoader, mount_apdat reformat, ENOSPC. Remaining source: the
TV's own update machinery downloading from the internet (app last ran
Nov 12 22:29; `ftpUpdateVersionFile.txt` = `V.0.51.19.0,V.0.51.52.5`
— the documented Medion downgrade makes the TV see a newer version).
`ap0` is byte-identical across SW versions (app updates ride the
`ap1` overlay), so an ap0 fingerprint alone cannot detect an applied
OTA — hence probe v9 compares ap1/nvt_sign/fs0/ker1 too.

**Probe v9 (staged 2026-11-13, read-only, awaiting run):** raw reads
first (ker1 head @`0x1440000` 256 KiB, `/conf` 10 MiB, `buffer`
16 MiB), then `ubi part fs0` + per-volume reads (`ap0` prefix,
`nvt_sign`, `fs0`, `ap1` full) with `if crc32` MATCH/DIFF markers vs
package values: ker1 `78cf514c`, ap0 `18def0da`, nvt_sign `29d846a8`,
fs0 `611b54a2`, ap1 `34d34070`; conf-unchanged `988a9672`,
buffer-head-unchanged `ed23b697`. RAM is zero-filled before each
`ubi read`, so a failed read shows as DIFF + an all-zero dump.
Markers `m9_*.bin` (`MTCH`/`DIFF`), `opentv_probe9_ran/done.bin`.

**Probe v9 (RAN 2026-11-13, partial — stop cause identified):** ran one
step (`opentv_probe9_ran.bin` = NVOK, `dump_ker1_head_v9.bin` captured)
and died at its FIRST `if crc32` line; all later markers/dumps missing
— far too early for a session-length cause (v21 moved ~460 MB fine).
Cause: v9's ker1 reference `78cf514c` was wrong-basis (package prefix
without the 64-byte uImage header; the real head crc is `f3f551c7`),
so the condition evaluated FALSE — and every `if crc32` that ever ran
on this U-Boot before (v1/v2/v21) evaluated TRUE and completed.
Hypothesis: a FALSE if-condition aborts the whole script (the else
path was never exercised). Regardless of mechanism: **probes must
contain zero `if` lines; all comparisons happen PC-side.**

**ker1 decoded (PC-side, round 9):** the TV's ker1 partition head is a
valid uImage header (`27 05 19 56`, hcrc ok, size `0x84bdf0` = exactly
the package `ker1.uimg` size, load=ep `0x02808000`, comp=1 gzip,
"Linux-4.9.118+", ts 1561516863) followed AT `0x40` by the package's
gzip payload **byte-identical** (dump has exactly one gzip magic, at
0x40, and `tv[0x40:] == pkg[:0x3ffc0]` exactly; dcrc field
`0x8b4154b7` == crc32(package)). The earlier "payload mismatch" was a
comparison artifact (position-wise compare ignoring the 64-byte
header shift + length-clamped slice). ⇒ ker1 == package, **no revert
evidence in ker1**. v9b ker1-head reference = `f3f551c7` (as-is dump).

**Probe v9b (staged 2026-11-13, read-only, awaiting run):** v9's plan
minus every `if` — pure dumps, PC-side comparison. Order: ker1 head
`0x1440000` 256 KiB, buffer head `0xed40000` 2 MiB, /conf `0xe340000`
10 MiB (raw), then `ubi part fs0` + ap0 prefix 256 KiB, nvt_sign full
`0x3e000`, fs0 full `0x592000`, ap1 full `0x1a66000`. RAM zero-filled
before every read (all-zero tail = failed/short read, not stale RAM).
No per-step markers: the dump files themselves are the progress
record; `opentv_probe9b_ran/done.bin` bracket the run. Expected CRCs:
ker1 `f3f551c7` (= v9 dump), buffer head `ed23b697` (= v8), conf
`988a9672` (= v8, + PC byte-diff), ap0 `18def0da` (= factory/v7),
nvt_sign `29d846a8`, fs0 `611b54a2`, ap1 `34d34070` (= package).
Interpretation: any DIFF on nvt_sign/fs0/ap1 = something wrote flash
on its own (interpret content: UBIFS journal churn = rw usage; new
assets = OTA); all MTCH = no self-writes in any dumped region.

**Probe v9b (RAN 2026-11-13, complete — all 7 dumps + done marker):**
the pure-dump channel works end-to-end; no `if` anywhere. Results:
`nvt_sign`, `fs0(vol)`, `ap1(vol)`, `ker1` head, `buffer` head all ==
package/v8-era exactly; /conf files byte-identical to v8 (the 733 KB
raw dump delta is UBIFS journal/index churn from rw remounts; file
trees diff clean, opentv_boot.log still 0 B, remote.txt/fto.bin
untouched). **LIVE ap0 == the v2.1 patched image** (prefix crc
`34e34d7e` exact, superblock mkfs_time/bytes_used identical) — 4 h
and many boot cycles after the v21 write. **No TV self-write
detected anywhere; no OTA applied.** The TV's current boot loop is
v2.1's own run_aurora.sh (HTTP fetch to unreachable :8123 → CIFS
fallback → appmgr relaunch).

**v7-fingerprint anomaly resolved as ghost (round 11):** v7 read ap0
= factory (`probe_ap0_factory.bin` = "FACT") *after* the v21 write
was verified — yet v9b sees v2.1 now, with no writer in between and
no possible 154 MB restore source (largest scratch: 23.25 MiB buffer,
empty; fs0 free ≈ 10 MiB; no network). A real flash rewrite to
factory is physically impossible. Working theory: after each
`ubi write` ap0 update the previous generation's PEBs stay
unmapped-but-not-erased; an attach resolving duplicate (vol_id,lnum)
claims returns old content on some boots (v7) and new on others
(v9b), aging out as WL erases old PEBs. No flash write involved.
Untested mechanism; v3.1's ap0/nvt_sign fingerprint trap will catch
any real reverter live if one exists.

**v3 write (BUILT & STAGED 2026-11-13, awaiting explicit go):**
`opentv_write_v3.scr` writes BOTH volumes in one boot, each with a
read-back CRC: ap0 ← `ap0_patched_v3.squashfs` (154,017,792 B
`0x92e2000`, crc `0xddfb3864`; debug-ini `program=/conf/opentv_payload`)
and conf ← `conf_v3.ubifs` (3,809,280 B `0x3a2000`, crc `0x96f6bd55`
= live round-8 `/conf` + `/conf/opentv_payload` mode 755; remote.txt
and fto.bin kept). Markers `v3_ap0_ok/FAIL.bin`, `v3_conf_ok/FAIL.bin`.
Payload v3.1 (stage1/launcher/opentv_payload.c, static ARM): telnetd
root shell on :23, `route del default` internet block re-asserted
every 30 s (run_aurora.sh's udhcpc renewals re-add the route; busybox
has no `ip` applet), ap0/nvt_sign fingerprint trap (baseline at boot,
re-check every 30 s, on ANY change dumps ps + /proc cmdlines to
`/conf/opentv_revert.log`), logs to `/conf/opentv_payload.log`.
Deployed ONLY as `kylo_usb_update.scr` on explicit go; parked on the
stick as `kylo_usb_update_WRITE-AP0CONF-v3_ARMED.scr`.

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
