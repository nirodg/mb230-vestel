# Dropbear SSH server for MB230

Port of [Dropbear](https://matt.ucc.asn.au/dropbear/dropbear.html), a small
SSH server and client, for the Vestel **17MB230** TV (Novatek NT72671/NT72673,
ARMv7 Cortex-A7, Linux 4.9 "Kylo", BusyBox userspace).

This is intended for use after you already have root access to the TV (for
example via the USB-injection root shell/telnet documented in the repo). It
provides a proper SSH server as an alternative to telnet.

## What is built

`build-docker.sh` cross-compiles **static** ARMv7 EABI5 hard-float binaries in
an `ubuntu:16.04` Docker container (matching the TV toolchain era used
elsewhere in this repo):

- `dropbear` — SSH server
- `dropbearkey` — host/user key generator
- `dbclient` — SSH client
- `scp` — file copy over SSH

Outputs go to `dropbear/out/`. Binaries are stripped and have no runtime
dependency on the TV's glibc.

## Build

```sh
cd dropbear
./build-docker.sh
# or: make
# optional: DROPBEAR_VERSION=2026.94 ./build-docker.sh
```

Requires Docker and network access (to fetch the Dropbear source tarball and
Ubuntu packages inside the container).

## Quick start on the TV

Assumes a root shell on the TV (e.g. `telnet <tv-ip> 23`) and that the TV and
PC are on the same LAN.

### 1. Upload binaries

From your PC, serve the `out/` directory:

```sh
cd dropbear/out
python3 -m http.server 8000
```

On the TV (root shell):

```sh
mkdir -p /tmp/ssh
cd /tmp/ssh
wget -O dropbear    http://<PC_IP>:8000/dropbear
wget -O dropbearkey http://<PC_IP>:8000/dropbearkey
chmod +x dropbear dropbearkey
```

> `/tmp` is usually tmpfs (lost on reboot). For persistence, copy to `/conf`
> (writable UBIFS), e.g. `/conf/dropbear/`, but keep `/conf` tidy and avoid
> storing large/unneeded files there.

### 2. Generate host keys (once)

Dropbear needs host keys. Generate them in persistent storage if you want them
to survive reboots:

```sh
mkdir -p /conf/dropbear
/tmp/ssh/dropbearkey -t rsa   -f /conf/dropbear/dropbear_rsa_host_key
/tmp/ssh/dropbearkey -t ed25519 -f /conf/dropbear/dropbear_ed25519_host_key
```

(You can generate only RSA if preferred; Ed25519 is smaller/faster if
supported by the build/client.)

### 3. Run the server

Foreground (useful for testing):

```sh
/tmp/ssh/dropbear -F -E -p 22 \
  -r /conf/dropbear/dropbear_rsa_host_key \
  -r /conf/dropbear/dropbear_ed25519_host_key
```

Background daemon:

```sh
/tmp/ssh/dropbear -p 22 \
  -r /conf/dropbear/dropbear_rsa_host_key \
  -r /conf/dropbear/dropbear_ed25519_host_key
```

Check it is listening:

```sh
netstat -ltn 2>/dev/null | grep ':22' || busybox netstat -ltn | grep ':22'
```

### 4. Connect from your PC

```sh
ssh root@<tv-ip>
```

**Authentication:** Dropbear uses the system account/password database
(`/etc/passwd`, `/etc/shadow`) like other SSH servers. On this platform root
may not have a usable password by default. Options:

- **Set a root password** (if `passwd` is available on the TV): `passwd root`
- **Public-key auth (recommended):** create `/root/.ssh/authorized_keys` (or
  the home directory configured for root) with your `~/.ssh/id_*.pub` line and
  correct permissions. Note: rootfs is often read-only; use a writable location
  and Dropbear's `-a`/authorized_keys handling as needed, or adjust config.
- **Blank-password login (LAN/testing only, insecure):** run with `-B` to allow
  blank passwords *if the account permits it*. Do not expose this beyond a
  trusted LAN.

You can also add your key from the TV side by pasting into an authorized_keys
file in a writable path and pointing Dropbear/user config accordingly, or by
temporarily enabling a permissive mode for first login and then locking it
down.

## Persistence across reboots

The jailbreak root shell in this repo is typically started by
`/conf/opentv_payload` (executed by the ap0 shim). To start Dropbear
automatically, you can extend that payload/keeper logic to:

1. ensure `/dev/pts` is mounted (`mount -t devpts devpts /dev/pts`), which the
   existing root-shell setup already does;
2. ensure host keys exist in `/conf/dropbear/`;
3. launch `/conf/dropbear/dropbear ...` if not already running (similar to how
   `telnetd` is kept alive).

Because the exact payload is device/session-specific and often rebuilt as part
of the USB-injection flow, integrate Dropbear into **your** deployed payload
image/script rather than modifying signed/stock partitions.

## Notes & troubleshooting

- **PTY required:** SSH sessions need PTYs. Mount devpts before starting
  Dropbear if not already mounted: `mount | grep devpts || mount -t devpts devpts /dev/pts`.
- **Static build:** binaries are linked statically (`-static`) for maximum
  compatibility with the TV environment. The linker may warn about NSS/libc
  functions in static binaries (`getpwnam`, `getspnam`, etc.); on this TV's
  Linux userspace with local `/etc/passwd`/`/etc/shadow` this is typically fine,
  but validate login behavior on your device.
- **Firewall/network:** ensure nothing on the TV/network blocks TCP/22.
- **Entropy:** Dropbear needs randomness (`/dev/urandom` should exist on
  Linux 4.9; key generation/login may hang without it).
- **`/conf` space:** keep host keys and binaries minimal; `/conf` is a small
  UBIFS volume.
- **Security:** prefer key auth over passwords/blank passwords. Telnet and an
  unauthenticated shell are insecure; treat SSH as the safer management path on
  a trusted LAN.
- **No warranty:** all use is at your own risk and intended for research on
  hardware you own.

## Files

- `build-docker.sh` — reproducible Docker cross-build
- `Makefile` — `make` / `make clean`
- `start-on-tv.sh` — helper to mount `/dev/pts`, generate host keys if missing,
  and start `dropbear` on the TV
- `out/` — prebuilt static ARMv7 binaries (`dropbear`, `dropbearkey`,
  `dbclient`, `scp`) produced by the build
- `.gitignore` — ignores `build-src/` and downloaded source tarballs
- `dropbear-<version>.tar.bz2` — downloaded source tarball (kept locally after
  build; gitignored)
