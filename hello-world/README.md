# hello-world (MB230 custom app proof)

Minimal proof that we can **create, upload, and run a custom app** on a Vestel
17MB230 TV ("Kylo", Novatek NT72671/NT72673, Linux 4.9, ARMv7 hard-float) via a
**telnet root shell**.

This directory is a self-contained example (source + Docker build script +
prebuilt binary + upload/run steps). It is intended to be used after you already
have a root shell on the TV (e.g. via the USB-injection jailbreak documented in
[`../README.md`](../README.md) and
[`../usb-injection/root-shell-v312/README.md`](../usb-injection/root-shell-v312/README.md)).

## Contents

- `hello.c` — source for the proof app
- `build-docker.sh` — reproducible ARM build using Docker (recommended)
- `Makefile` — `make docker` (preferred) or native `make`
- `hello` — first prebuilt hello-world binary (ARMv7 EABI5, static, stripped)
- `shell-aliases.sh` — optional zsh/bash aliases for build/serve helpers

## What it does

`hello`:

- prints `Hello, world from MB230!` to stdout
- prints its PID/UID/GID
- writes a proof marker to `/tmp/hello_world_proof.txt` on the TV

## Prerequisites

- A root telnet shell on the TV (default port 23 in the v3.12 root-shell
  milestone): `telnet <tv-ip> 23`
- TV and PC on the same LAN (for network upload methods)
- Docker (recommended build path), or native cross toolchain
  (`gcc-arm-linux-gnueabihf`)
- BusyBox `wget` and/or `nc` on the TV (present in this firmware)

## Build (Docker, recommended)

Always-build-with-Docker script:

```sh
cd hello-world
./build-docker.sh
# or: make docker
```

This produces/refreshes `./hello` as a stripped, statically-linked ARM binary:

```sh
file hello
# hello: ELF 32-bit LSB executable, ARM, EABI5 ...
```

A prebuilt `hello` binary is included in this directory as the first
hello-world proof artifact; rebuild it with `./build-docker.sh` after changing
`hello.c` or to reproduce locally.

## Build (native toolchain)

```sh
sudo apt install gcc-arm-linux-gnueabihf
cd hello-world
make
```

Dynamic linking is not recommended unless you match the TV glibc (`make STATIC=`).

## Shell aliases (zsh/bash)

To add convenience aliases (`mb230-hello-build`, `mb230-hello-serve`), source
the provided file from your shell rc:

```sh
# ~/.zshrc or ~/.bashrc
source /media/dorin/more_data/work/mb230-vestel/hello-world/shell-aliases.sh
```

Then:

```sh
mb230-hello-build   # builds hello via Docker
mb230-hello-serve   # serves this directory on :8000 for wget upload
```

## Upload directly via telnet

Pick one method. Run commands **inside the telnet session on the TV** unless
noted.

### Method A — HTTP + `wget` (recommended)

1. On the PC, serve the `hello-world/` directory (includes prebuilt `hello`):

   ```sh
   cd hello-world
   python3 -m http.server 8000
   # or: mb230-hello-serve
   ```

   (Allow the port through your firewall if needed, e.g.
   `sudo ufw allow 8000/tcp`.)

2. On the TV (telnet shell), download, make executable, and run:

   ```sh
   cd /tmp
   wget -O hello http://<PC_IP>:8000/hello
   chmod +x hello
   ./hello
   ```

### Method B — `nc` (netcat)

BusyBox `nc` variants differ; the form below works with the common
"listen then receive" pattern. Use a free port (example: `9999`).

1. On the TV (telnet shell), listen and write the incoming file:

   ```sh
   nc -l -p 9999 > /tmp/hello
   ```

2. On the PC, in another terminal, send the binary:

   ```sh
   cd hello-world
   nc <TV_IP> 9999 < hello
   ```

3. Back on the TV (after `nc` finishes), run it:

   ```sh
   chmod +x /tmp/hello
   /tmp/hello
   ```

> Note: if your BusyBox `nc` uses different flags, adapt the listen command
> (e.g. `nc -ll -p 9999 > /tmp/hello`). Method A (`wget`) is usually simpler.

## Expected result

```text
Hello, world from MB230!
pid=1234 uid=0 gid=0
proof written to /tmp/hello_world_proof.txt
```

Verify:

```sh
cat /tmp/hello_world_proof.txt
```

## Notes

- `/tmp` is convenient for transient tests (often tmpfs). `/conf` is persistent
  writable storage on this platform; avoid cluttering it and remove test
  binaries when done.
- `chmod +x` is required after upload.
- Static linking is preferred to avoid glibc/toolchain mismatches on the TV.
- This proves userland code execution over telnet; it does not install a
  persistent service or modify boot/signed partitions.
- Do not publish firmware images, TV dumps, or device secrets alongside this
  proof.
- `hello` is the included first hello-world binary artifact; link/reference it
  from other docs or tools as needed (e.g. `hello-world/hello`).
