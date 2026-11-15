#!/usr/bin/env python3
"""Passive UART logger: waits for communication, then logs to ~/logs-tv.txt.

Opens the serial port and sits idle until the TV starts sending data
(you trigger reboot/power-on yourself). Everything received is written
as timestamped text to ~/logs-tv.txt and echoed to stdout.

Usage:
    python3 uart_wait_log.py [-p /dev/ttyUSB0] [-b 115200] [-o ~/logs-tv.txt]

Stop with Ctrl-C. Requires pyserial.
"""
import argparse
import os
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial missing: pip install --user pyserial")


def ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    ap.add_argument("-o", "--out", default=os.path.expanduser("~/logs-tv.txt"))
    args = ap.parse_args()

    out_path = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    try:
        ser = serial.Serial(args.port, args.baud, bytesize=8, parity="N",
                            stopbits=1, timeout=1)
    except Exception as e:
        sys.exit(f"cannot open {args.port}: {e}")

    print(f"[{ts()}] waiting for UART data on {args.port} @ {args.baud} -> {out_path}")
    print(f"[{ts()}] trigger the TV yourself (reboot/power-on). Ctrl-C to stop.", flush=True)

    seen = False
    buf = b""
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(f"\n[{ts()}] === session start {args.port}@{args.baud} ===\n")
        f.flush()
        try:
            while True:
                try:
                    chunk = ser.read(4096)
                except Exception as e:
                    msg = f"[{ts()}] read error: {e}"
                    print(msg, flush=True); f.write(msg + "\n"); f.flush()
                    time.sleep(0.5)
                    try:
                        ser.close()
                    except Exception:
                        pass
                    try:
                        ser = serial.Serial(args.port, args.baud, timeout=1)
                        msg = f"[{ts()}] reopened {args.port}"
                        print(msg, flush=True); f.write(msg + "\n"); f.flush()
                    except Exception:
                        time.sleep(1)
                    continue

                if not chunk:
                    continue
                if not seen:
                    seen = True
                    msg = f"[{ts()}] communication detected ({len(chunk)} bytes)"
                    print(msg, flush=True); f.write(msg + "\n"); f.flush()

                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = "".join(
                        chr(c) if 32 <= c < 127 or c in (9,) else f"<{c:02x}>"
                        for c in line
                    )
                    out = f"[{ts()}] {text}"
                    print(out, flush=True)
                    f.write(out + "\n")
                    f.flush()
        except KeyboardInterrupt:
            pass
        finally:
            if buf:
                text = "".join(chr(c) if 32 <= c < 127 or c in (9,) else f"<{c:02x}>" for c in buf)
                out = f"[{ts()}] {text}"
                print(out, flush=True); f.write(out + "\n")
            f.write(f"[{ts()}] === session end ===\n")
            f.flush()
    try:
        ser.close()
    except Exception:
        pass
    print(f"[{ts()}] saved to {out_path}")


if __name__ == "__main__":
    main()
