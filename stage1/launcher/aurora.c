/* OpenTV first-payload launcher, built to be dropped in as the stock
 * app's `aurora.elf` via a firmware-run hook (see OPENTV.md Stage 2).
 *
 * Goals for the FIRST on-TV run (deliberately minimal / low-risk):
 *   1) prove OUR code runs inside the stock app environment,
 *   2) leave durable evidence even with no serial: a log file written to
 *      CWD and to /conf (both readable back over USB / the dump channel),
 *   3) a visible on-screen signal: fill /dev/fb0 (honours the pan offset,
 *      the stock display parks the visible buffer at a non-zero yoffset).
 *
 * libc only, builds -static: no glibc-version or libmali dependency on
 * the first shot. GPU (libmali/EGL/GLES) reuse comes in a later payload.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <time.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include <sys/utsname.h>
#include <linux/fb.h>

static void logline(FILE *f, int argc, char **argv) {
    struct utsname u; char cwd[512];
    time_t t = time(NULL);
    if (!f) return;
    fprintf(f, "[opentv-aurora] ran at epoch %ld\n", (long)t);
    if (uname(&u) == 0)
        fprintf(f, "  uname: %s %s %s %s\n", u.sysname, u.release, u.version, u.machine);
    if (getcwd(cwd, sizeof cwd)) fprintf(f, "  cwd: %s\n", cwd);
    fprintf(f, "  argv0: %s  argc: %d\n", argc ? argv[0] : "?", argc);
    const char *envs[] = {"PWD","LD_LIBRARY_PATH","FRAMEBUFFER","HOME","PATH",0};
    for (int i = 0; envs[i]; i++) {
        const char *v = getenv(envs[i]);
        fprintf(f, "  env %s=%s\n", envs[i], v ? v : "(unset)");
    }
    fflush(f);
}

static void write_logs(int argc, char **argv) {
    const char *paths[] = {"opentv_aurora.log", "/conf/opentv_aurora.log",
                           "/tmp/opentv_aurora.log", 0};
    for (int i = 0; paths[i]; i++) {
        FILE *f = fopen(paths[i], "a");
        if (f) { logline(f, argc, argv); fclose(f); }
    }
}

static void fill_fb(void) {
    int fd = open("/dev/fb0", O_RDWR);
    if (fd < 0) return;
    struct fb_var_screeninfo v; struct fb_fix_screeninfo fx;
    if (ioctl(fd, FBIOGET_VSCREENINFO, &v) || ioctl(fd, FBIOGET_FSCREENINFO, &fx)) {
        close(fd); return;
    }
    unsigned bpp = v.bits_per_pixel ? v.bits_per_pixel : 32;
    unsigned long stride = fx.line_length ? fx.line_length : (v.xres * bpp / 8);
    unsigned long need = stride * (v.yres_virtual ? v.yres_virtual : v.yres);
    unsigned char *fb = mmap(NULL, need, PROT_READ|PROT_WRITE, MAP_SHARED, fd, 0);
    if (fb == MAP_FAILED) { close(fd); return; }
    /* honour the visible pan offset so we draw into the on-screen buffer */
    unsigned long base = (unsigned long)v.yoffset * stride + (unsigned long)v.xoffset * (bpp/8);
    for (unsigned y = 0; y < v.yres; y++) {
        unsigned char *row = fb + base + (unsigned long)y * stride;
        for (unsigned x = 0; x < v.xres; x++) {
            unsigned char *px = row + x * (bpp/8);
            px[0] = 0x80; px[1] = 0x00; px[2] = 0x80;      /* purple (BGR) */
            if (bpp == 32) px[3] = 0xff;
        }
    }
    munmap(fb, need);
    close(fd);
}

int main(int argc, char **argv) {
    write_logs(argc, argv);
    fill_fb();
    /* STAY ALIVE. idtv exiting makes the stock watchdog reboot the TV
     * (that was the reboot loop). A launcher must not return. Re-fill the
     * framebuffer periodically (the stock display can pan/flip buffers)
     * and re-stamp the log so we can see it kept running. */
    unsigned long i = 0;
    for (;;) {
        sleep(5);
        fill_fb();
        if ((++i % 6) == 0) write_logs(argc, argv);   /* ~every 30s */
    }
    return 0;   /* unreachable */
}
