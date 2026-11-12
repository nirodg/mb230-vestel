# Cross-compile the Stage-1 PoC launcher for the MB230 (ARMv7 hard-float).
#
# Needs an armhf toolchain (interpreter /lib/ld-linux-armhf.so.3) and the
# stock EGL/GLES headers + the stock libEGL.so/libGLESv2.so stubs copied
# from the TV dump (ap0/lib + Khronos headers).
#
#   make CROSS_COMPILE=arm-linux-gnueabihf- SYSROOT=/path/to/stock-libs
#
# SYSROOT must contain:  include/EGL/*.h include/GLES2/*.h  lib/libEGL.so lib/libGLESv2.so
# (headers: Khronos EGL/GLES2; the .so are the stock stubs from ap0/lib.)

CROSS_COMPILE ?= arm-linux-gnueabihf-
CC    := $(CROSS_COMPILE)gcc
SYSROOT ?= ./stocklibs

CFLAGS  := -O2 -marm -mfpu=neon -mfloat-abi=hard -I$(SYSROOT)/include
LDFLAGS := -L$(SYSROOT)/lib -lEGL -lGLESv2 -lm

opentv_launcher: opentv_launcher.c
	$(CC) $(CFLAGS) $< -o $@ $(LDFLAGS)
	@file $@ | grep -q 'ARM' && echo "[ok] ARM binary built" || echo "[!] check arch"

clean:
	rm -f opentv_launcher
