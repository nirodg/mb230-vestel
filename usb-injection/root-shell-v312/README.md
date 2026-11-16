# MB230 USB injection — root shell milestone (v3.12) 🎉

**Status (Nov 15 2026): STABLE ROOT SHELL ACHIEVED on a fully-functional TV** (Horizon 50HL7530U/B, Vestel 17MB230 / Novatek NT72671/73, Linux 4.9.118 "Kylo", aurora.elf idtv app).

```
/mtd_apexe/board # id
uid=0(root) gid=0(root)
/mtd_apexe/board # uname -a
Linux (none) 4.9.118+ #2 SMP PREEMPT Wed Apr 1 14:12:52 CST 2020 armv7l GNU/Linux
```

> Research on owned hardware. No firmware images or device secrets are published here.

## How it works (final architecture)
1. **U-Boot USB auto-update channel** (`kylo_usb_update.scr` on FAT32 stick, hold **OK** at power-on): unsigned script runs, writes/verifies UBI volumes with read-back CRC + stick markers.
2. **ap0 patch v3.2.1** (verified on device): tiny static ARM shim at `/vendor/opentv_shim`, `data/nvt.app.debug.ini` `[idtv] program=/vendor/opentv_shim` (`name=idtv` keeps argv[0] semantics for appmgr). Shim execs `/bin/sh /conf/opentv_payload`.
3. **conf wrapper v3.12** (`/conf/opentv_payload`, apdat0 rw UBIFS):
   - **Restores the full stock `run.sh` env** (~80 exports: `BROWSER_DIR=/vendor/browser_dir`, `WORKING_PATH`, `DFBHOME`, `GST_*`, `NVT_*`, ...) — the shim's exec dropped environ, which caused aurora's `FATAL:base_paths_tvsdk.cc(72) browser_dir does not exist` SIGABRT loop (v3.6–v3.10).
   - Background keeper (survives exec): mounts **devpts** at `/dev/pts` (busybox telnetd needs a PTY; without it :23 accepts then resets), starts/maintains **`telnetd -l /bin/sh -p 23`**, `busybox nc -ll -p 2323 -e /bin/sh` fallback, snapshots `/tmp/stdout.all` + `ps` to `/conf`, heartbeats.
   - `exec /mtd_apexe/board/com.nvt.idtv/aurora.elf` → stock aurora becomes `idtv` and satisfies appmgr/privserver/watchdog liveness (`wait for IDTV semaphore done`).

## Access
- TV connects via WiFi (wlan0) to the LAN; recent IPs: `192.168.0.111` (also seen .177, .136 wired in earlier sessions). MAC `cc:d3:c1:9e:00:e1` (wlan) / `D4:E2:CC:EC:45:E9` (wired).
- `telnet <tv-ip> 23` → root shell (`/bin/sh`, cwd `/mtd_apexe/board`). Port `2323` = nc fallback (one shot per connection).
- Shell survives as long as the TV runs; keeper re-arms telnetd every ~3s.
- **SSH (Dropbear):** a ported Dropbear server + on-TV installer is available at
  [`../tools/dropbear/`](../tools/dropbear/README.md) (installs to `/conf/dropbear`,
  keeps telnet available). Use it for proper SSH access once root shell is up.

## Conf write (v3.12) — the only USB step needed to reproduce
| Item | Value |
|---|---|
| Script | `opentv_write_conf_v312.scr` (copy to stick root as `kylo_usb_update.scr`) |
| Image | `conf_v312.ubifs` (3,809,280 B / `0x3a2000`, CRC32 `0x155e4c25`) — **not included** (contains device state; build from your own apdat0 dump) |
| Markers | `confv312_began.bin` (`5a5a5a5a`), `v312_conf_ok.bin` (`NVOK`) |
| Target | `apdat0` (`ubi part apdat0; ubi write … 0x3a2000`), read-back CRC verified |

Prerequisite: ap0 v3.2.1 shim already written (`opentv_write_ap0_v321.scr`, image CRC `0x10e50fc0`). Probe: `opentv_probe_v10.scr` dumps `/conf`. Restore: `ap0_restore.scr` (factory ap0).

## Key facts learned (see repo docs for full evidence)
- `/dev/pts` is not mounted by stock init — telnetd/ssh need it mounted manually.
- aurora requires the full stock env; missing env → `browser_dir` FATAL SIGABRT → watchdog reboot (~20-25s loop) **after** passing the IDTV semaphore handshake (white screen/square = aurora rendering mid-boot).
- appmgr idtv liveness: `wait_for_idtv=y`, `semaphore_idtv` handshake + privserver (`COM.NVT.PRIVSERVER(.CB)`) + watchdog kicking all handled by running stock aurora as the idtv process (sidecar-before-exec pattern).
- `/conf/enable_coredump` (create the file) enables core dumps from aurora's crash handler.

## Constraints / safety
- Boot chain is signature-verified; do **not** flash unsigned boot components (XBOOT/SECOS/U-Boot/kernel/FDT). Userspace volumes (ap0/apdat0/buffer) are writable via the U-Boot channel.
- Scripts <8 KB, end with `%`; apdat0 must be first/only UBI attach for conf writes; verify read-back CRCs; keep restore images.
- Never publish firmware images, dumps, or device secrets.
