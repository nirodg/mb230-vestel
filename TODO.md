# TODO

## Map all remote IR buttons (persistent task)

**Status:** in progress — infrastructure ready, mapping data incomplete.

We can intercept every decoded remote key (`otv_port` + `mempatch` tap/suppress,
see `usb-injection/tools/opentv-port/docs/IR_INPUT.md`), but only a few key ids
are currently labeled. Goal: a complete, authoritative table of every button on
the remote → ice key id → `ice_keymapping_db.xml` name, and a reusable tool so
anyone can map a remote in the future.

### Known so far (ice key ids, from `squash_ap0/ice_keymapping_db.xml` + on-device logs)

| Button | Key id (dec) | Hex | Notes |
|---|---|---|---|
| VolumeUp | 544 | 0x220 | on-device verified |
| VolumeDown | 545 | 0x221 | on-device verified |
| Exit | 528 | 0x210 | on-device verified |
| Power | 543 | 0x21F | allowlist (passes to aurora) |
| Source/AV (KeyAux) | 552 | 0x228 | allowlist (assumed — confirm) |
| Sleep | 574 | 0x23E | allowlist |
| Up | 522 | 0x20A | on-device verified (nav) |
| Down | 523 | 0x20B | on-device verified (nav) |
| Left | 524 | 0x20C | |
| Right | 525 | 0x20D | |
| OK/Select | 526 | 0x20E | on-device verified |

Release codes = press code + 2000 (0x7D0).

### Tasks

- [ ] Press every button with `otv_port` running and collect press/release
      codes from `tail -f /tmp/otv_port.log` (or the on-screen PRESS/REL
      counters) into a full table above.
- [ ] Verify the assumed mappings (Source/AV = 552, etc.) and catch buttons
      whose codes are NOT in `ice_keymapping_db.xml` (e.g. some remotes send
      codes outside the standard table).
- [ ] Build a reusable **key-mapping tool**: a small listener (PC-side is
      enough) that connects to the otv_port IPC socket (or tails its log) and
      prints the `ice_keymapping_db.xml` *name* for each incoming key id, so
      any future remote can be mapped by pressing buttons. Candidate
      implementations:
      - PC-side Python: read `ice_keymapping_db.xml` + `vk_keymapping_db.xml`,
        listen on a unix socket / parse `otv_port.runtime.log`, print
        `0x221 -> KeyVolumeDown`.
      - On-TV: extend `otv_port` nav label with the key name lookup (needs the
        keymap parsed at build time).
- [ ] Commit the completed key table into `usb-injection/tools/opentv-port/docs/IR_INPUT.md`
      (or a dedicated `KEYMAP.md`).
- [ ] Add the reverse direction (key id → synthetic injection via `send_key`)
      so the tool can also *simulate* a remote button — useful for CI/scripts.
- [ ] **Reverse the proprietary GPU stack for hardware rendering** — the Open TV
      UI currently rasterises on the CPU (software, XRGB8888 into a DirectFB
      surface). The SoC has a Novatek NVTGA GPU (DirectFB/Graphics: "Novatek
      NVTGA GPU 1.0" + `libmali` GLES blobs in the vendor image). Goal: a
      `kms-gles2`-style gateway backend that renders the UI through the vendor
      GLES (GBM/EGL or DirectFB GL) so frames are composited on the GPU.
      Sub-tasks:
      - [ ] Inventory the vendor GL stack (`libmali.so`, `libEGL`/`libGLESv2`,
            `/dev/ntkgpu`, DirectFB `gfxdrivers`) in `squash_ap0`.
      - [ ] Determine the render path aurora uses (DirectFB GL surface? EGL on
            DirectFB? raw ntkgpu ioctls?).
      - [ ] Prototype an EGL-on-DirectFB / GLES context that blits the UI
            texture, benchmark vs the CPU rasteriser.
      - [ ] Implement `gw_display` GLES backend behind the same API
            (`device.conf [display] backend = gles2`), keeping the CPU path as
            fallback.
      - [ ] No proprietary blobs may be *required* — keep CPU rendering the
            default; GLES is an optional accelerator (Open TV design rule).

### Notes / constraints

- The mempatch is in-memory only and address-pinned to this firmware build
  (`aurora.elf` sha256 `c7f1c7b5…6084b`); re-apply after aurora restart.
- Keep `mempatch restore` / reboot as the recovery path while testing.
- DVB/HDMI-CEC and the front-panel keypad may generate codes through other
  paths (`ice_LocalKeyEventGetThread`); the remote table above is UART-IR only.
