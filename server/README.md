# CIFS rig — run OpenTV's `aurora.elf` on the TV over the LAN

Temporary dev rig on your PC. The TV mounts a Samba share and runs our
`aurora.elf` from it via the stock `/conf/remote.txt` hook — so you iterate
the binary by re-copying one file, with **no further TV flash writes**.

## Confirmed launch chain (this firmware)
`/vendor/run.sh` (RUN_APPMGR=1) → `/conf/remote.txt` present →
`appmgr --applist=nvt.app.debug.ini` → `debug.ini` idtv program is
`run_aurora.sh` → it brings up eth0 (MAC `D4:E2:CC:EC:45:E9`), DHCP,
`insmod cifs.ko`, mounts `//<PC>/mb230cifs` at `/conf/remotelf`, and with
`isgdb=0` runs **`/conf/remotelf/aurora.elf`** directly = our binary.

**Hardware-verified status of each stage (2026‑11‑13, after the Track‑C
ap0 patch + `insmod ntkethmac.ko`):**
1. eth0 exists (forced MAC on the wire) — ✅
2. DHCP lease — ✅ (192.168.0.136)
3. ARP + TCP to PC :445 — ✅
4. SMB1 negprot (NT LM 0.12) + SPNEGO/NTLMSSP negotiate — ✅
5. NTLMSSP AUTHENTICATE — ❌ **client aborts** (kernel lacks
   `hmac(md5)`/`md4`/`des`/`arc4`; see ARCHITECTURE.md round 6) ⇒
   mount fails ⇒ reboot loop persists
6. run our aurora.elf — blocked on 5

## Fix plan (ap0 patch v2 — BUILT & STAGED 2026-11-13, awaiting go)
CIFS cannot work without kernel crypto the TV doesn't have, and Samba
cannot avoid client-side crypto. So the v2 `ap0` patch replaces the
CIFS mount + exec block in `run_aurora.sh` with:

```sh
if [ -e /conf/aurora.elf ]; then
    exec /conf/aurora.elf                        # network-free path wins
fi
if timeout 20 wget -O /conf/remotelf/aurora.elf http://$ip_addr:8123/aurora.elf; then
    chmod +x /conf/remotelf/aurora.elf
    exec /conf/remotelf/aurora.elf               # plain HTTP, no crypto
fi
# ... original CIFS block kept as harmless last resort
```

- `$ip_addr` still comes from `/conf/remote.txt` — the PC address
  stays configurable there without reflashing.
- busybox `wget` + `timeout` applets verified present in the TV rootfs.
- Iteration loop: replace `/srv/mb230cifs/aurora.elf` on the PC →
  next TV reboot fetches the new binary. (`/conf/aurora.elf`, if ever
  installed, overrides HTTP — remove it to go back to iterating.)
- PC side (server already running as of 2026-11-13):
  `python3 -m http.server 8123 -d /srv/mb230cifs`
  (+ `sudo ufw allow 8123/tcp` — **user action needed**; port 8000 is
  occupied by another service on this PC, hence 8123).
- Build/write: `stage1/uboot/ap0_write_v2.scr` +
  `ap0_patched_v2.squashfs` (154,017,792 B, crc32 `0x11a83e1b`).

## Environment notes (current rig)
- **PC is on WiFi** (`wlp5s0`), currently 192.168.0.100 — the same IP
  `remote.txt` points at by coincidence. Make it permanent with a
  router DHCP reservation for the PC's WiFi MAC, or the experiment
  breaks silently whenever the lease changes.
- The **TV must stay wired** (ethernet): the remote.txt path only
  brings up eth0.
- ufw is active on the PC; :445 was confirmed reachable (a full SMB1
  session was established). Any new server port (e.g. :8000 HTTP)
  needs an explicit allow.
- Samba config in use: `server min protocol = NT1`, `ntlm auth = yes`
  (`smb-compat-oldcifs.conf`) — proven to negotiate SMB1 with the
  TV's kernel 4.9 CIFS client.

## One-time PC setup
```
make -C stage1/launcher aurora.elf         # or the docker build (README there)
sudo server/setup_cifs.sh                  # installs samba, creates share+user
```
It prints the `remote.txt` line: `0:<PC-ip>:mb230:<password>`.
Requirements: TV + PC on the **same Ethernet LAN** (the hook uses eth0, not Wi-Fi).

## Arming (the one TV flash write — needs your go)
Because the service menu can't drop `remote.txt` and U-Boot can't write a
single file, `remote.txt` is placed by rewriting the whole `/conf` volume
once (current `/conf` + `remote.txt`), via the U-Boot `.scr` channel.
```
# make the RESTORE stick first (recovery net), verify you can read it back:
stage1/uboot/track_b_stick.sh restore --dump <dump_apdat0.bin> --stick /media/you/STICK
# then the WRITE stick:
stage1/uboot/track_b_stick.sh write --ip <PC> --user mb230 --pass <pw> \
    --dump <dump_apdat0.bin> --stick /media/you/STICK
```
Boot the TV **holding OK** to perform the write. On the next normal boot the
TV runs our `aurora.elf`: purple framebuffer + a log at `/conf/opentv_aurora.log`
(read it back with the dump probe).

## If anything looks wrong
Power-cycle + hold OK (U-Boot is untouched/signed) and run the **restore**
stick — `dump_apdat0.bin` is already on the write stick too. Worst case
without restoring is a `/conf` factory reset, not a brick. All writes stay
confined to `apdat0`; never add a write to any boot/signed partition.

## Security / hygiene
LAN-only share (`hosts allow` is set), a dedicated nologin user, read-only
export. Tear it down when done: remove the `[mb230cifs]` block from
`/etc/samba/smb.conf`, `smbpasswd -x mb230`, `rm -rf /srv/mb230cifs`.
Don't expose it to the internet.

## How the TV reaches the PC (analysis) + failure modes
`run_aurora.sh` (triggered by `/conf/remote.txt`) connects over **eth0
(cable) only** — Wi-Fi is never used:
`insmod cifs.ko; ifconfig eth0 down; ifconfig eth0 hw ether D4:E2:CC:EC:45:E9;
ifconfig eth0 up; udhcpc ...; mount -t cifs //PC/mb230cifs /conf/remotelf;
/conf/remotelf/aurora.elf`.

### ROOT CAUSE #2 — confirmed 2026‑11‑13 (round 6, post ap0‑patch)
**NTLMSSP auth is impossible: the kernel has no crypto for it.** After
the Track‑C patch fixed the missing driver, the TV reached the PC's
smbd over SMB1 and then hung up mid‑auth (FIN ~0.5 s after SYN, no
AUTHENTICATE ever sent). The TV's `cifs.ko` needs `hmac(md5)`
(NTLMv2), `md4`+`des` (NTLMv1), or `ecb(arc4)` — none are built into
`ker1` and no crypto `.ko` ships in any volume. Samba cannot choose an
auth flavor that avoids client-side crypto (plaintext auth was removed
from Samba long ago). ⇒ **the CIFS transport is a dead end on stock
kernels; use plain HTTP instead** (see "Fix plan" above).

### ROOT CAUSE #1 — confirmed 2026‑11‑13 (round‑4 live dumps + captures)
**The ethernet driver is never loaded in the remote.txt path.** `ap0`
(full 10 MiB `apdat0` dump + two wired captures during power‑cycled
boots, `NVOK` probe marker):

- The Track‑B conf write **succeeded and is live**: `remote.txt` is on
  the TV with our content, the whole `/conf` UBI has since been
  organically rewritten by the TV itself (erase counters 1–13,
  scatter‑attached layout) — the TV booted Linux with our image
  repeatedly. Not a flash/UBIFS problem.
- **`ntkethmac.ko` is only ever `insmod`ed by `script_network.sh`, and
  the only caller of `script_network.sh` in the whole firmware is the
  stock `com.nvt.idtv/aurora.elf`** (string `./script_network.sh`
  inside the binary). `run.sh` never calls it; `gstreamer.sh` (its only
  shell reference) is called by nothing.
- With `remote.txt` present, appmgr launches `run_aurora.sh` *instead
  of* the stock app ⇒ `eth0` does not exist ⇒ all three `ifconfig`
  calls fail, `udhcpc` exits instantly, `mount.cifs` fails,
  `$REMOTELF/aurora.elf` is missing ⇒ FG app gone ⇒ reset ⇒ the
  black‑screen reboot loop. Zero TV frames ever reached the wire (two
  captures) and smbd never logged a TV connection — consistent with a
  missing interface, not a DHCP/SMB failure.
- The stock path works (official FW wired is fine) because the stock
  app loads the driver itself.

The earlier "blocking `udhcpc` wedges the UI" theory is superseded: the
plain `udhcpc` is only reached after `ifconfig`, which never succeeds.

### No network-free exec hook exists on this firmware (audited 2026‑11‑13)
- `/conf/run_with_dwelf` path: dead — `data/nvt.app.dwelf.ini` does not
  exist in the read‑only volume.
- `run_nfs.sh`/`telnetd` block in `run.sh`: dead — `run_nfs.sh` is
  absent.
- `/conf/standalone_browser.bin`: only toggles `RUN_BROWSER_STANDALONE`
  env exports; no ini app points at a `/conf` binary.
- `/conf/en_kblast_msg` (debugfs), `/conf/force_enable_coredump`,
  `refresh_conf_permission`: no exec.

⇒ The remote.txt path **requires** eth0, and eth0 requires a load of
`ntkethmac.ko` inside the remote path ⇒ **Track‑C: patch `run_aurora.sh`
in the `ap0` volume** (one added `insmod /vendor/modules/ntkethmac.ko`
line). See `../stage1/uboot/README.md`.

Failure modes (now historical, kept for reference):
1. **Blocking `udhcpc`** — carved `run_aurora.sh` (confirmed against
   MD30010 `ap0`, 2026‑11‑13) runs a **plain** `udhcpc -s ... eth0`:
   no `-n`/`-t`/`-T` ⇒ it retries forever without a lease and the UI
   app blocks, `idtv` never readies, and the **watchdog reboots** before
   it reaches the PC. (The stock aurora path gives up after ~4 s:
   `udhcpc -q --release -T 2 -n -t 2 -A 0` — see `ARCHITECTURE.md`.)
   The forced `eth0 down`+MAC change (`D4:E2:CC:EC:45:E9`) renegotiates
   the link and adds to the window. This script is in read-only
   /vendor — we can't fix it.
2. **SMB version mismatch**: TV `cifs.ko` (kernel 4.9) negotiates SMB1/NT1;
   modern Samba 4.19 disables SMB1 by default → mount fails. Fix with
   `smb-compat-oldcifs.conf` (`server min protocol = NT1`, `ntlm auth = yes`).
   (Already applied on this rig; still the next failure to expect once
   eth0 comes up.)

Implications for retry (post Track‑C):
- After the ap0 patch, the next expected gate is **DHCP**: plain
  `udhcpc` (no `-n`) retries forever, so a slow carrier is survivable;
  a router refusing `D4:E2:CC:EC:45:E9` would show DISCOVER without
  OFFER in a capture.
- Next expected gate is **SMB1**: watch smbd logs (`log.<tv-ip>`).
- `remote.txt` still sits on the boot-critical UI path: until the
  experiment is over, every normal boot takes it. The restore image
  (round‑4 full `apdat0` dump) removes it in one gated write.
