# Cross-compile MB230 GUI Hello World (framebuffer + input test) for ARMv7.
# Preferred: build via Docker (no host toolchain required).
#
#   ./build-docker.sh
#   # or: make docker

CROSS_COMPILE ?= arm-linux-gnueabihf-
CC      := $(CROSS_COMPILE)gcc
ARMFLAGS := -O2 -marm -mfloat-abi=hard
STATIC  ?= -static

TARGET := gui_hello

all: $(TARGET)

$(TARGET): gui_hello.c
	$(CC) $(ARMFLAGS) $(STATIC) $< -o $@
	$(CROSS_COMPILE)strip $@ 2>/dev/null || true
	@file $@ | grep -q ARM && echo "[ok] $(TARGET) (ARM$(if $(STATIC), static,))" || echo "[!] check arch"

docker:
	./build-docker.sh

clean:
	rm -f $(TARGET)

.PHONY: all docker clean
