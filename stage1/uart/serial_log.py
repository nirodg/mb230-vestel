#!/usr/bin/env python3
"""Passive UART boot logger for the 17MB230 console.

CP2102 (TV TX -> adapter RX, GND <-> GND, nothing else connected),
TV console is 115200 8N1 (evidence: fdt0.dts uart@fd091000 baud
0x1c200; kernel cmdline console=ttyS0,115200).

Usage:
    python3 serial_log.py [-p /dev/ttyUSB0] [-b 115200] [-o FILE]

Prints a timestamped decode to the screen and appends the raw byte
stream to FILE (default uart_boot_<date>.raw). Non-printable bytes
are shown as <hex> so wrong-baud garbage is obvious (real console
output is clean ASCII lines).

Stop with Ctrl-C. Requires pyserial only.
"""
import argparse
import datetime
import os
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial missing: pip install --user pyserial")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    ap.add_argument("-o", "--out",
                    default=datetime.datetime.now().strftime("uart_boot_%Y%m%d_%H%M%S.raw"))
    ap.add_argument("--show-hex", action="store_true",
                    help="print every chunk as hex instead of decoded text")
    args = ap.parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, bytesize=8,
                            parity="N", stopbits=1, timeout=1)
    except serial.SerialException as e:
        sys.exit(f"cannot open {args.port}: {e}")

    print(f"logging {args.port} @ {args.baud} 8N1 -> {args.out} "
          f"(Ctrl-C to stop)", flush=True)
    t0 = time.monotonic()
    buf = b""
    with open(args.out, "ab") as raw:
        try:
            while True:
                chunk = ser.read(4096)
                if not chunk:
                    continue
                raw.write(chunk)
                raw.flush()
                if args.show_hex:
                    print(f"[{time.monotonic()-t0:8.3f}] {chunk.hex(' ')}", flush=True)
                    continue
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    ts = time.monotonic() - t0
                    text = "".join(chr(c) if 32 <= c < 127 or c in (9,)
                                   else f"<{c:02x}>" for c in line)
                    print(f"[{ts:8.3f}] {text}", flush=True)
        except KeyboardInterrupt:
            pass
    print(f"\nstopped; raw stream in {args.out} ({os.path.getsize(args.out)} bytes)")


if __name__ == "__main__":
    main()
