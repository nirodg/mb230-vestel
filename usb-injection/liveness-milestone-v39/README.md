# MB230 USB injection — liveness milestone (v3.9)

**Status/milestone (Nov 2026, Horizon 50HL7530U/B, Vestel 17MB230 / Novatek NT72671/73, Linux 4.9 "Kylo"):** we can hook `idtv` via the U-Boot USB auto-update script channel and keep the process alive long enough that **appmgr’s IDTV semaphore handshake completes** and **stock `aurora.elf` starts rendering** (observed: Medion/logo → white screen → white square/cursor-like element, persisting across reboots) before `idtv` exits and the watchdog resets (~20–25s cycle, `COM.NVT.PRIVSERVER.CB` flood / exit flow). This is major progress toward a stable root shell and customized vendor-based (userspace) firmware.

> Research on owned hardware. No firmware images or device secrets are published here.

## What’s on the TV (when following this flow)
- **ap0 (mounted `/vendor`, ro SquashFS in UBI/`fs0`)**: patched **v3.2.1** with a tiny shim at `/vendor/opentv_shim` and `data/nvt.app.debug.ini` `[idtv] program=/vendor/opentv_shim`, `name=idtv` (keeps `argv[0]=idtv` semantics for appmgr). Written/verified via `stage1/uboot/opentv_write_ap0_v321.scr` (image CRC `0x10e50fc0`, `0x92e3000`).
- **apdat0 (mounted `/conf`, rw UBIFS)**: `opentv_payload` wrapper executed by the shim. v3.9 hides `/conf/remote.txt` temporarily, runs `run_aurora.sh`’s normal (local `aurora.elf`) path for full idtv liveness, restores `remote.txt`, keeps `telnetd -l /bin/sh -p 23` + diagnostics, and snapshots `/tmp/stdout.all` to `/conf/opentv_stdout_all.log`.

## Current USB injection (conf v3.9, conf-only iteration)
Armed, reversible, conf-only write (ap0 shim already in place):

| Item | Value |
|---|---|
| Script | `opentv_write_conf_v39.scr` (copy to stick root as `kylo_usb_update.scr`) |
| Image | `conf_v39.ubifs` (3,809,280 B / `0x3a2000`, CRC32 `0xaf8b1171`) — **not included** (see below) |
| Markers | `confv39_began.bin` (`5a5a5a5a`), `v39_conf_ok.bin` (`NVOK`) / `v39_conf_FAIL.bin` |
| Target | `apdat0` (`ubi part apdat0; ubi write … apdat0 0x3a2000`), read-back CRC verified |

**Why the conf image is not included:** `/conf` UBIFS images embed device-specific state and may contain secrets/credentials (e.g. `remote.txt`, MAC/profile material). Build your own from a dump of *your* `apdat0` with the desired `opentv_payload` wrapper, and compute the CRC/size to match the script (or regenerate the script). Do not publish dumps or device secrets.

## How to use (high level)
1. FAT32 USB stick, `kylo_usb_update.scr` at root = the armed script for the step you intend (writes are gated by the script you place there).
2. **Conf write (v3.9):** TV off → stick in → power on **holding OK** ~1–2 min → power off → check markers on stick (`v39_conf_ok.bin` = `NVOK`). Normal boot (no OK-hold) to test.
3. **Probe/read-only dump:** use `opentv_probe_v10.scr` (as `kylo_usb_update.scr`) to dump `/conf` to `dump_apdat0_v10.bin` for analysis.
4. **Restore:** `ap0_restore.scr` restores factory ap0 image (keep a known-good factory image/CRC as documented in scripts).

## Key scripts (this folder / repo)
- `opentv_write_ap0_v321.scr` — ap0 shim v3.2.1 (verified on device).
- `opentv_write_conf_v39.scr` — current conf iteration (runs stock aurora via `run_aurora.sh` normal path for liveness).
- `opentv_probe_v10.scr` — read-only `/conf` dump.
- Repo refs: `stage1/uboot/README.md`, `ARCHITECTURE.md`, `RESEARCH.MD` — constraints, evidence, and findings.

## Constraints / safety
- U-Boot USB scripts run unsigned but the boot chain is verified; do **not** flash unsigned boot components. Prefer conf-only iterations; ap0 writes proven but always keep/verify restores.
- Probes/writes: fresh session, `apdat0` as first/only UBI attach for conf; compare read-backs by CRC; scripts <8 KB, end with `%`.
- Never commit/publish firmware images, flash dumps, or device secrets (keys, DRM material, MAC/serials, credentials).
