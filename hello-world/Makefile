# Cross-compile the MB230 "Hello, world" proof app (ARMv7 hard-float).
#
# Preferred (no host toolchain required):
#   make docker
#   # or: ./build-docker.sh
#
# Native toolchain (Debian/Ubuntu):
#   sudo apt install gcc-arm-linux-gnueabihf
#   make
#
# The TV rootfs ships glibc 2.23. Build statically by default so the binary
# does not depend on the TV's libc vintage or loader.

CROSS_COMPILE ?= arm-linux-gnueabihf-
CC      := $(CROSS_COMPILE)gcc
ARMFLAGS := -O2 -marm -mfloat-abi=hard
STATIC  ?= -static

TARGET := hello

all: $(TARGET)

$(TARGET): hello.c
	$(CC) $(ARMFLAGS) $(STATIC) $< -o $@
	$(CROSS_COMPILE)strip $@ 2>/dev/null || true
	@file $@ | grep -q ARM && echo "[ok] $(TARGET) (ARM$(if $(STATIC), static,))" || echo "[!] check arch"

# Reproducible build using Docker (ubuntu:16.04 cross toolchain).
docker:
	./build-docker.sh

clean:
	rm -f $(TARGET)

.PHONY: all docker clean
