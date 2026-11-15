# Session notes — root access, exploration, and flash backup (2026-11-15)

## Context
- TV: Horizon 50HL7530U/B (Vestel 17MB230, Novatek NT72671/NT72673 "Kylo")
- Root shell obtained via USB-injection jailbreak (v3.12 milestone, see `usb-injection/root-shell-v312/README.md`, `README.md`).
- Telnet reachable at **192.168.0.111:23** (root, `/bin/sh`, cwd `/mtd_apexe/board`), verified during this session. `nc` fallback also exposed on **2323** per milestone docs.

## System inventory (live)

### Kernel / CPU / memory
- `uname -a`: `Linux (none) 4.9.118+ #2 SMP PREEMPT Wed Apr 1 14:12:52 CST 2020 armv7l GNU/Linux`
- `/proc/cpuinfo`: 4x ARMv7 Processor rev 4 (v7l), Cortex-A53 (as reported), BogoMIPS ~24, Features include neon/vfpv4/lpae/crypto (aes/sha1/sha2/crc32 etc.)
- `/proc/meminfo`: MemTotal ~738312 kB, SwapTotal 358396 kB (zram0 358400 blocks)

### BusyBox / tools
- `BusyBox v1.29.3 (2019-02-22 09:47:02 CST)`, ~343 applets
- Available: `nc`, `wget`, `tftp`, `dd`, `gzip`, `tar`, `md5sum`, `sha256sum`, etc.

### Mounts / storage layout
- `/` — squashfs (ro) from `/dev/root`
- `/vendor` — squashfs (ro) on `/dev/ubiblock0_1` (also over `/lib/firmware`, `/mtd_apexe/board`)
- `/vendor2` — squashfs (ro) on `/dev/ubiblock0_2`
- `/conf` — **ubifs (rw)** on `ubi13_0` (~3.4M, ~23% used)
- `/buffer` and `/mtd_rwarea` — **ubifs (rw)** on `ubi14_0` (~232.5M)
- `/tmp` — tmpfs (rw, 36M), `/dev/shm` tmpfs, `/media` tmpfs (empty)
- `/dev/pts` — devpts mounted (rw) — present in this session
- No USB mass storage mounted (`/sys/block` showed no sdX; `/media` empty)

### MTD partitions (`/proc/mtd`)
| dev  | size (hex) | erasesize | name     | bytes       |
|------|------------:|----------:|----------|------------:|
| mtd0 | 00100000    | 00040000  | xboot    | 1,048,576   |
| mtd1 | 00100000    | 00040000  | ddrcfg   | 1,048,576   |
| mtd2 | 000c0000    | 00040000  | ddrbud   | 786,432     |
| mtd3 | 00140000    | 00040000  | xbootdat | 1,310,720   |
| mtd4 | 000c0000    | 00040000  | npt      | 786,432     |
| mtd5 | 00240000    | 00040000  | misc     | 2,359,296   |
| mtd6 | 00280000    | 00040000  | secos    | 2,621,440   |
| mtd7 | 00140000    | 00040000  | uboot    | 1,310,720   |
| mtd8 | 00140000    | 00040000  | fdt0     | 1,310,720   |
| mtd9 | 00140000    | 00040000  | fdt1     | 1,310,720   |
| mtd10| 00700000    | 00040000  | ker0     | 7,340,032   |
| mtd11| 00c00000    | 00040000  | ker1     | 12,582,912  |
| mtd12| 0c300000    | 00040000  | fs0      | 204,472,320 |
| mtd13| 00a00000    | 00040000  | apdat0   | 10,485,760  |
| mtd14| 11000000    | 00040000  | buffer   | 285,212,672 |
| mtd15| 00180000    | 00040000  | logo     | 1,572,864   |

MTD block devices `/dev/mtdblock0..15` present. SPI flash controller/devices visible in sysfs (`/sys/.../spiflash`, `fd081000.spi`, `/dev` has no direct `spi*` node) — **SPI flash content not dumped in this step** (needs appropriate interface/method; investigate `/dev/ntkspi`/spi subsystem before assuming MTD coverage).

### Notable runtime observations
- Stock UI running: `aurora.elf` (PID ~1683), `com.nvt.appmgr --applist=/vendor/data/nvt.app.debug.ini`, etc.
- Jailbreak keeper active: `sh /conf/opentv_payload`, `telnetd -l /bin/sh -p 23`, `busybox nc -ll -p 2323 -e /bin/sh`.
- IR/input: `/dev/ttyS2` is UART IR (DirectFB `nvt_uart_ir`), open by aurora and others; `/dev/ntgpio` open; no evdev remote nodes (only mice). Keymaps in `/vendor/ice_keymapping_db.xml`, `/vendor/vk_keymapping_db.xml` (no `KeyHome` string found).

## NAND/MTD backup procedure (performed)

**Goal:** dump partitions before making changes. No USB storage mounted and `/tmp` too small for large images, so dumps were streamed over LAN to the PC.

- **PC:** 192.168.0.100. Dumps originally received in `/tmp/opencode/mb230-flash-backup/` and moved to **`/media/dorin/more_data/work/mb230-full-backup/`** (durable workspace storage).
- **TV:** 192.168.0.111
- **Method (per partition):** on PC `nc -l -p <port> > mtdN_name.bin`, on TV `dd if=/dev/mtdN bs=65536 2>/tmp/dd.log | nc 192.168.0.100 <port>` then verify byte count/md5.
- **Orchestration:** `backup_mtd.sh` (ports 9100+N), logs in `backup_run.log`, checksums in `checksums.md5`, manifest in `manifest.tsv`.
- **Status:** backup completed (`backup_run.log`: `ALL DONE`). **15/16 partitions dumped successfully with expected sizes** (xboot,ddrcfg,ddrbud,xbootdat,npt,secos,uboot,fdt0,fdt1,ker0,ker1,fs0,apdat0,buffer,logo). **`mtd5 (misc, 2359296 bytes)` failed:** `dd: /dev/mtd5: Input/output error` on TV (both `/dev/mtd5` and `/dev/mtdblock5` produced 0 bytes) — could indicate bad/unreadable blocks or device-specific read issue; not recovered in this session.

**Example (manual, verified):**
```sh
# PC
nc -l -p 9104 > mtd4_npt.bin
# TV
dd if=/dev/mtd4 bs=65536 2>/tmp/dd.log | nc 192.168.0.100 9104; cat /tmp/dd.log
# result: 786432 bytes, md5 a6ff4947628e6f6974b9a445b0315101
```

## Safety / next steps
- **Do not** write to flash partitions blindly; keep dumps offline/safe before experimentation.
- SPI NOR (if separate from dumped MTDs) still needs identification and backup.
- Backups stored at `/media/dorin/more_data/work/mb230-full-backup/` (verify/copied to additional safe/offline storage as needed).
- After backup verification: proceed with `gui-hello-world/` takeover test (`/tmp/run-on-tv.sh` on TV) to validate framebuffer + remote input in our app (note: stopping aurora affects UI/watchdog; reboot recovers).

## Files created in repo this session (for reference)
- `hello-world/` — telnet-uploadable "Hello World" app proof (Docker build, prebuilt binary, aliases/docs).
- `gui-hello-world/` — framebuffer GUI "Hello World" + remote/input test (Docker build, prebuilt binary).
- `ir-sequence-poc/` — on-TV IR/remote raw monitor script.
- `SESSION_2026-11-15_ROOT_BACKUP.md` — this note.
