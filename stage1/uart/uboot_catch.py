#!/usr/bin/env python3
"""Robust U-Boot catcher: logs serial, auto-interrupts autoboot, probes UBIFS."""
import argparse, time, sys, re
import serial

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-p','--port', default='/dev/ttyUSB0')
    ap.add_argument('-b','--baud', type=int, default=115200)
    ap.add_argument('-o','--out', default='/tmp/opencode/uart_uboot.raw')
    args = ap.parse_args()
    log = open(args.out,'ab')
    buf = b''
    interrupted = prompt_seen = cmds_sent = False
    t0 = time.time(); cmd_i = 0; last_send = 0
    cmd_seq = [
        b'\r\n', b'help\r\n', b'ubi part apdat0\r\n',
        b'ubifsmount ubi0:apdat0\r\n', b'ubifsmount ubi0\r\n',
        b'ubifsls /\r\n', b'ubifsls /conf\r\n',
        b'ubifsload 0x3300000 /opentv_wrapper.log\r\n',
        b'ubifsload 0x3300000 opentv_wrapper.log\r\n',
        b'md.b 0x3300000 0x600\r\n',
        b'fatls usb 0:auto\r\n',
    ]
    def emit(chunk):
        nonlocal buf
        if not chunk: return
        log.write(chunk); log.flush()
        try:
            sys.stdout.write(chunk.decode('utf-8', errors='replace')); sys.stdout.flush()
        except Exception: pass
        buf = (buf + chunk)[-16384:]
    def open_ser():
        while True:
            try:
                s = serial.Serial(args.port, args.baud, timeout=0.2)
                emit(b'\n[[serial open]]\n')
                return s
            except Exception as e:
                emit(f'\n[[open err {e}]]\n'.encode()); time.sleep(1)
    ser = open_ser()
    emit(b'\n[[LISTENING]]\n')
    try:
        while time.time() - t0 < 900:
            try:
                chunk = ser.read(4096)
            except Exception as e:
                emit(f'\n[[read err {e}]]\n'.encode())
                try: ser.close()
                except Exception: pass
                time.sleep(0.5); ser = open_ser(); continue
            if chunk: emit(chunk)
            text = buf.decode('utf-8', errors='replace')
            low = text.lower(); now = time.time()
            if not interrupted:
                if any(t in low for t in ['hit any key','autoboot','stop autoboot']):
                    for _ in range(12):
                        try: ser.write(b'\x03\r\n \r\n')
                        except Exception: pass
                        time.sleep(0.05)
                    emit(b'\n[[sent interrupt]]\n'); interrupted = True; last_send = now
            if not prompt_seen and interrupted:
                if re.search(r'(\n|^)[^\n]{0,50}(=>|# |> ) *$', text):
                    prompt_seen = True; emit(b'\n[[prompt detected]]\n'); last_send = now
            if prompt_seen and not cmds_sent and now - last_send > 1.8:
                if cmd_i < len(cmd_seq):
                    try: ser.write(cmd_seq[cmd_i])
                    except Exception as e: emit(f'\n[[write err {e}]]\n'.encode())
                    emit(f'\n[[sent cmd {cmd_i}]]\n'.encode()); cmd_i += 1; last_send = now
                    if cmd_i == len(cmd_seq): cmds_sent = True; emit(b'\n[[cmd sequence done]]\n')
        emit(b'\n[[timeout]]\n')
    except KeyboardInterrupt: pass
    finally:
        try: ser.close()
        except Exception: pass
        log.close()
if __name__ == '__main__': main()
