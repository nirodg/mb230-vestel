# ir-sequence-poc: remote button monitor (MB230)

Best-effort on-TV script to observe/display raw remote/IR button events.

## Background (this firmware)

- IR is handled in userspace (not evdev): DirectFB `libdirectfb_nvt_uart_ir.so`.
- Relevant devices: `/dev/ttyS2` (UART IR) and `/dev/ntgpio`.
- On a live TV, `aurora.elf` and other processes already hold these devices open, so
  a passive userland reader may **not** see events (data consumed by existing readers)
  or may need careful handling to avoid interfering with normal remote input.
- Keymaps: `/vendor/ice_keymapping_db.xml` (e.g. `KeyNine=521`), `/vendor/vk_keymapping_db.xml`
  (e.g. `KeyNine=1009`); no `KeyHome` name found in keymaps on tested unit.

## Script

- `tv-button-monitor.sh` — runs on the TV (BusyBox/sh). Tails candidate interfaces and
  writes/logs raw hex bytes when received.

## Upload & run (via telnet root shell)

Assumes TV reachable at e.g. `192.168.0.111:23` and PC serves files.

On PC:

```sh
cd ir-sequence-poc
python3 -m http.server 8000
```

On TV (telnet):

```sh
cd /tmp
wget -O tv-button-monitor.sh http://<PC_IP>:8000/tv-button-monitor.sh
chmod +x tv-button-monitor.sh
# run (Ctrl-C to stop)
./tv-button-monitor.sh
# or timed run (e.g. 15s)
DUR=15 ./tv-button-monitor.sh
```

Logs/captures are written under `/tmp/ir-monitor/` (`ttyS2.hex`, `ntgpio.hex`, `ttyS2.raw`).

## Interpreting results

- If hex bytes appear when pressing keys, record the patterns for `Home` and `9` (and
  repeats/release behavior) to define a sequence detector (e.g. `Home + 9,9,9,9`).
- If output stays empty while keys are pressed, the active IR consumers likely own the
  data path; next steps may require protocol-aware tapping of the driver interface,
  temporary controlled instrumentation, or an alternative capture method.

## Safety

- Do not change tty/device settings on a production session unless you accept possible
  remote-input disruption.
- Runs in userspace on `/tmp`; does not modify boot/signed partitions.
