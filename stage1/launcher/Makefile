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
# Static by default: the TV's glibc vintage is unknown (old 4.9 BSP), so a
# dynamically-linked binary risks "GLIBC_2.xx not found" / interpreter
# mismatch. fbshow uses only basic libc (no NSS), so -static is safe and
# removes that whole failure class. Override with STATIC= for a dynamic build.
STATIC ?= -static
fbshow: fbshow.c
	$(CC) $(ARMFLAGS) $(STATIC) $< -o opentv_fbshow
	$(CROSS_COMPILE)strip opentv_fbshow 2>/dev/null || true
	@file opentv_fbshow | grep -q ARM && echo "[ok] opentv_fbshow (ARM$(if $(STATIC), static,))" || echo "[!] check arch"

# T2 — EGL/fbdev GLES2 via the stock libmali (resolved at runtime on the TV).
# Link against libmali.so DIRECTLY, not the libEGL/libGLESv2 shims: on the
# MB230 those shims are ~2.8 KB hand-built forwarders whose .dynsym has a
# malformed sh_info, so GNU ld resolves zero symbols from them. libmali.so
# exports the full EGL+GLES set (SONAME libmali.so), and run.sh puts
# /vendor/lib on LD_LIBRARY_PATH so it loads at runtime. GLLIB overrides the
# lib if a porter's TV has proper shims instead.
GLLIB ?= -lmali
TV_GLIBC_MINOR ?= 23
launcher: opentv_launcher.c
	$(CC) $(ARMFLAGS) -mfpu=neon -I$(SYSROOT)/include $< -o opentv_launcher \
	      -L$(SYSROOT)/lib -Wl,-rpath-link,$(SYSROOT)/lib $(GLLIB) -lm
	@file opentv_launcher | grep -q ARM && echo "[ok] opentv_launcher (ARM)" || echo "[!] check arch"
	@# The MB230 rootfs ships glibc 2.23. A newer toolchain silently adds
	@# e.g. __libc_start_main@GLIBC_2.34 and the binary dies before main().
	@if readelf -V opentv_launcher | grep -Eo 'GLIBC_2\.[0-9]+' | \
	    awk -F. '$$2>$(TV_GLIBC_MINOR){bad=1} END{exit !bad}'; then \
	  echo "[!] opentv_launcher needs glibc > 2.$(TV_GLIBC_MINOR) (TV has 2.$(TV_GLIBC_MINOR)) - use an Ubuntu 16.04 toolchain"; \
	  rm -f opentv_launcher; exit 1; fi

# Copy whatever was built into board/ and (optionally) onto a FAT32 stick.
stick:
	cp -v run* 2>/dev/null || true
	-cp -v opentv_fbshow opentv_launcher $(BOARD)/ 2>/dev/null
	@echo "board/ ready. Copy it to the stick:"
	@echo "  cp -r $(BOARD) $(STICK)/"

clean:
	rm -f opentv_fbshow opentv_launcher
