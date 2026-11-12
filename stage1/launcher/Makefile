# Cross-compile the Stage-1 PoC binaries for the MB230 (ARMv7 hard-float).
#
# Toolchain (Debian/Ubuntu):  sudo apt install gcc-arm-linux-gnueabihf
#
#   make fbshow                         # T0: no vendor libs needed
#   make launcher SYSROOT=./stocklibs   # T2: needs stock EGL/GLES stubs+headers
#   make stick STICK=/media/you/USB     # assemble board/ onto a FAT32 stick
#
# SYSROOT (T2 only, BYO — never committed) must contain:
#   include/EGL/*.h include/GLES2/*.h   (Khronos headers)
#   lib/libEGL.so lib/libGLESv2.so      (stock stubs from your TV's ap0/lib)

CROSS_COMPILE ?= arm-linux-gnueabihf-
CC      := $(CROSS_COMPILE)gcc
SYSROOT ?= ./stocklibs
ARMFLAGS := -O2 -marm -mfloat-abi=hard

BOARD := ../board

# T0 — framebuffer picture, plain libc only.
fbshow: fbshow.c
	$(CC) $(ARMFLAGS) $< -o opentv_fbshow
	@file opentv_fbshow | grep -q ARM && echo "[ok] opentv_fbshow (ARM)" || echo "[!] check arch"

# T2 — EGL/fbdev GLES2 via the stock libmali (resolved at runtime on the TV).
launcher: opentv_launcher.c
	$(CC) $(ARMFLAGS) -mfpu=neon -I$(SYSROOT)/include $< -o opentv_launcher \
	      -L$(SYSROOT)/lib -lEGL -lGLESv2 -lm
	@file opentv_launcher | grep -q ARM && echo "[ok] opentv_launcher (ARM)" || echo "[!] check arch"

# Copy whatever was built into board/ and (optionally) onto a FAT32 stick.
stick:
	cp -v run* 2>/dev/null || true
	-cp -v opentv_fbshow opentv_launcher $(BOARD)/ 2>/dev/null
	@echo "board/ ready. Copy it to the stick:"
	@echo "  cp -r $(BOARD) $(STICK)/"

clean:
	rm -f opentv_fbshow opentv_launcher
