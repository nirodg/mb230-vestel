#!/usr/bin/env python3
"""Minimal raw terminal for the 17MB230 UART console (pyserial only).

For the interactive U-Boot shell: U-Boot waits bootdelay=60 and any
keypress interrupts autoboot. Start this BEFORE powering the TV,
press Enter a few times during the U-Boot banner, and you get the
U-Boot prompt. Also works as a root-shell terminal later.

Usage:
    python3 serial_term.py [-p /dev/ttyUSB0] [-b 115200]

Quit with Ctrl-] (like telnet). Terminal is put in raw mode; the
console is 115200 8N1. Requires pyserial only.
"""
import argparse
import select
import sys
import termios
import tty

try:
    import serial
except ImportError:
    sys.exit("pyserial missing: pip install --user pyserial")

QUIT = b"\x1d"  # Ctrl-]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    args = ap.parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, bytesize=8,
                            parity="N", stopbits=1, timeout=0)
    except serial.SerialException as e:
        sys.exit(f"cannot open {args.port}: {e}")

    print(f"terminal on {args.port} @ {args.baud} 8N1 — Ctrl-] to quit",
          file=sys.stderr, flush=True)

    old = termios.tcgetattr(sys.stdin)
    tty.setraw(sys.stdin.fileno())
    try:
        while True:
            r, _, _ = select.select([sys.stdin, ser], [], [], 0.1)
            if sys.stdin in r:
                data = sys.stdin.read(1).encode()
                if data == QUIT:
                    break
                if data:
                    ser.write(data)
            if ser in r:
                data = ser.read(4096)
                if data:
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        print("bye", file=sys.stderr)


if __name__ == "__main__":
    main()
