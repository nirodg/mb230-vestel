# Build Dropbear SSH for MB230 (ARMv7 hard-float, static).
# Requires Docker (recommended): builds inside ubuntu:16.04 with
# gcc-arm-linux-gnueabihf, matching the TV's glibc era.
#
#   make            # download source (if needed) and build via Docker
#   make clean      # remove build output (keeps downloaded tarball)
#   make distclean  # also remove downloaded tarball

VERSION ?= 2026.94

all: docker

docker:
	DROPBEAR_VERSION=$(VERSION) ./build-docker.sh

clean:
	rm -rf out build-src

distclean: clean
	rm -f dropbear-*.tar.bz2 dropbear-*.tar.bz2.asc

.PHONY: all docker clean distclean
