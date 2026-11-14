# UART console prep (hardware on order, 2026-11-13)

Ordered: a CP2102 USB–UART bridge and a "C177.ULA24MHZ" 24 MHz 8-ch
USB logic analyzer (the common FX2LP clone; supported by sigrok /
PulseView via the `fx2lafw` firmware). This file collects what the
firmware already tells us and the bring-up plan, so wiring day is
plug-and-play. Nothing here requires opening the TV beyond accessing
the mainboard's service pads.

## What the firmware guarantees (evidence, no guessing)

- The console UART is `uart@fd091000`, `compatible = "ns16550a"`,
  `baud = <0x1c200>` = **115200 8N1** (`fdt0.dts`).
- U-Boot env: `stdin/stdout/stderr = serial@0,fd091000`,
  `baudrate=115200`, **`bootdelay=60`** — U-Boot waits a full minute
  and any keypress interrupts autoboot → **interactive U-Boot shell**
  (strictly more powerful than our `.scr` channel: `help`, `md/mm`,
  `ubi` commands, `fatls` — no more stick round-trips).
- Kernel cmdline (`fdt0` /chosen): `console=ttyS0,115200
  no_console_suspend earlyprintk` — the kernel + `init` + `run.sh`
  echo everything to this port, including **every echo in
  `run_aurora.sh`**: "Remote config file is found", "reading
  /conf/remote.txt", "mount cifs", `insmod` errors, mount failures.
  This is exactly the visibility we lacked in rounds 1–5.
- The SoC exposes several ns16550a UARTs (`fd090000`, `fd091000`,
  `fd092000`, `fd093000` in `fdt0.dts`); the console is the
  `fd091000` one, but which *board pads* route to it is **TBD** —
  find by measurement (below), not assumption.

## CP2102 wiring (bring-up day)

1. TV off, board accessible. Find **GND** first (continuity to a
   screw boss / USB shell).
2. Find the console **TX** pad: logic analyzer on candidate pads,
   PulseView UART @ 115200, power the TV — the pad that streams
   U-Boot/kernel output is TX. (Idle-high ~3.3 V is a hint, but let
   the decode decide.) **Caution:** the remote control is **IR over
   UART** on this platform (see OPENTV.md — one of the other
   ns16550a UARTs), so a pad that only bursts when you press remote
   keys is the IR line, not the console; keep looking.
3. Connect: TV **TX → CP2102 RX**, TV **RX → CP2102 TX**, GND↔GND.
4. **Never connect the CP2102 5V/VCC output to the TV.** The board
   powers its own UART; we only tap TX/RX/GND. 3.3 V logic — the
   CP2102 must be set/verified for 3.3 V signaling (most modules have
   a 3.3/5V jumper or are 3.3 V logic with 5V-tolerant… verify per
   module; when in doubt a series 1k resistor on RX is a cheap
   protector).
5. Terminal: no picocom/screen on this host and no sudo — use
   `stage1/uart/serial_log.py` (passive timestamped boot capture,
   pyserial, which IS installed) and `stage1/uart/serial_term.py`
   (raw interactive terminal for the U-Boot bootdelay=60 window;
   quit = Ctrl-]).

## What UART unlocks (ordered by payoff)

1. **Live watch of the remote.txt path** — the exact line where
   `run_aurora.sh` fails (or now, with the ap0 patch, the `insmod
   ntkethmac.ko` result, DHCP lease, CIFS mount, our ELF's stderr).
2. **Interactive U-Boot shell** at boot (`bootdelay=60`) — instant
   dumps/writes without the USB stick dance; also `saveenv` becomes
   possible but we deliberately **don't** (env is redundantly stored
   by boot firmware; keep our no-saveenv discipline).
3. **Root shell, two routes:**
   - U-Boot: interrupt autoboot, `run bootcmd`-style manual boot with
     a modified cmdline (`init=/bin/sh`) if the kernel accepts it —
     kernel signature checks are done by U-Boot `verify=y`, cmdline
     lives in `fdt0` which U-Boot loads to RAM; test non-destructively
     by editing the RAM FDT before booting.
   - ap0 patch (we now own that channel): flip `RUN_SHELL=1` in
     `run.sh` → `pcbconfig -i -w 0` + shell on console. One more
     607-PEB rewrite, same verified pipeline.
4. Debug logs from `com.nvt.appmgr` (log4cxx `[debug] enable_*` are
   already `y` in the debug ini path we're booted into).

## Logic analyzer (C177 ULA 24 MHz 8ch)

- Host software: **PulseView** (not yet installed; `sudo apt install
  pulseview` — includes `fx2lafw`). The device enumerates as a
  Cypress FX2; PulseView loads the firmware on attach.
- Uses here: pin-finding above; sniffing the **SPI NOR** (CS/CLK/MOSI
  of the `sf` device) during a probe boot to watch XBOOT boot reads
  live; IR remote decode; I2C (EDID/audio codec) if we go there.
  24 MHz sampling is comfortable for 115200 UART and for SPI clocks
  up to a few MHz.
- Channels are labeled on the silk; treat inputs as **3.3 V max**
  (these clones are not reliably 5 V tolerant).

## Status

- [x] Firmware facts collected (above)
- [x] CP2102 + logging scripts ready (`serial_log.py`, `serial_term.py`;
      pyserial 3.5 present, no picocom/screen on host — no sudo needed)
- [ ] Board pad identification (GND / TX / RX) — needs the board
      accessible; passive TX-hunt = CP2102 RX on candidate pad + GND,
      boot TV, readable ASCII at 115200 = console TX (garbage = wrong
      pad or wrong baud; IR-remote bursts = the IR UART, not console)
- [ ] First console capture of a normal boot
- [ ] First U-Boot interrupt (`bootdelay=60` window)
