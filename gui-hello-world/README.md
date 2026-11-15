# gui-hello-world (MB230 GUI + remote input test)

Second proof app: a **GUI "Hello World"** for Vestel 17MB230 that draws a simple
interface directly to the framebuffer and listens for remote/controller input, so
you can test that your app can render on-screen and receive button events.

## What it does

`gui_hello` (static ARM binary):

- Renders a fullscreen UI to `/dev/fb0` (direct fbdev, no EGL/GPU libs): title
  "HELLO WORLD", status text, and 4 button blocks.
- Opens `/dev/ttyS2` (UART IR, `nvtir`) and `/dev/ntgpio` (non-blocking, raw
  mode on tty) and polls for incoming bytes.
- On any received input, flashes/highlights a button, shows "INPUT RECEIVED!",
  updates event count/last source/last bytes (hex) on screen, and prints details
  to stderr/log.

This is intended as an **input/display integration test** for your own app.

## Contents

- `gui_hello.c` — framebuffer UI + input polling source
- `build-docker.sh` / `Makefile` — Docker-first build (recommended)
- `run-on-tv.sh` — helper to run on TV after stopping stock UI (takeover test)
- `gui_hello` — prebuilt ARMv7 static binary (if present/built)

## Build (Docker, recommended)

```sh
cd gui-hello-world
./build-docker.sh
# or: make docker
```

Produces `./gui_hello` (`ELF 32-bit ARM, EABI5, statically linked`).

## Upload via telnet

Prereq: root telnet shell on TV (e.g. `192.168.0.111:23`).

On PC:

```sh
cd gui-hello-world
python3 -m http.server 8000
```

On TV:

```sh
cd /tmp
wget -O gui_hello http://<PC_IP>:8000/gui_hello
wget -O run-on-tv.sh http://<PC_IP>:8000/run-on-tv.sh
chmod +x gui_hello run-on-tv.sh
```

## Run / test

### Important: display & input ownership

- While **`aurora.elf` (stock UI)** is running it owns the display pipeline and
  reads `/dev/ttyS2` for IR. Running `gui_hello` alongside it may result in
  **no visible UI** and/or **no remote events received** by this app.
- To properly test "remote works with our new app", run `gui_hello` as the
  foreground/display owner (stop aurora/idtv first) so it can read input and draw.

### Takeover test (recommended for validation)

From the TV telnet shell:

```sh
/tmp/run-on-tv.sh
```

This stops `aurora.elf`/idtv/appmgr and execs `gui_hello`. Press remote buttons:
- if the app receives data from IR/GPIO, you should see **INPUT RECEIVED!**, a
  highlighted button, updated counters/hex, and stderr logs like
  `[gui-hello] ttyS2 N bytes: ...`.

**Recovery:** stopping stock UI may trigger watchdog/reboot behavior depending on
state; if the screen is stuck after exiting, reboot/power-cycle the TV. Your
telnet root shell access (if provided by the jailbreak keeper) may persist until
reboot, but plan for recovery.

### Non-takeover (quick check)

```sh
/tmp/gui_hello
```

Useful to confirm the binary runs, but display/input results may be limited while
aurora is active.

## Notes

- Decodes raw input bytes (not mapped to key names). Correlate received hex
  patterns with physical button presses to identify codes/sequences.
- Framebuffer format is assumed 32/24/16bpp; rendering is best-effort.
- Do not modify boot/signed partitions; this is a userland test binary.
- `Ctrl-C` (in the running session) exits the app (`SIGINT` handler). If run as
  the only foreground UI, use telnet to start/stop as needed.
