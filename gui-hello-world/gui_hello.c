/*
 * MB230 GUI Hello World (framebuffer) + remote input test.
 *
 * - Draws a simple UI directly to /dev/fb0 (no EGL/GPU libs required).
 * - Listens for raw input bytes from /dev/ttyS2 (UART IR) and /dev/ntgpio.
 * - Any received input event highlights on-screen buttons/status so you can
 *   verify the remote/controller works in this app.
 *
 * NOTE: On a live system, aurora.elf may own /dev/ttyS2 and the display.
 * For a clean test, stop the stock UI first (e.g. kill aurora) so this app
 * can take over input/display, then reboot to recover if needed.
 */

#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/select.h>
#include <sys/time.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

static volatile int g_run = 1;
static void on_sig(int s) { (void)s; g_run = 0; }

typedef struct {
    int fd;
    uint8_t *fb;
    size_t smem_len;
    int w, h, bpp, stride;
    long base;
} FB;

static uint32_t rgb(FB *fb, uint8_t r, uint8_t g, uint8_t b) {
    /* Assume 32bpp ARGB/XRGB or 24bpp BGR; write per-component safely. */
    (void)fb;
    return (0xffu << 24) | ((uint32_t)r << 16) | ((uint32_t)g << 8) | b;
}

static void put_px(FB *fb, int x, int y, uint8_t r, uint8_t g, uint8_t b) {
    if (x < 0 || y < 0 || x >= fb->w || y >= fb->h) return;
    uint8_t *p = fb->fb + fb->base + (long)y * fb->stride + (long)x * fb->bpp;
    if (fb->bpp == 4) {
        p[0] = b; p[1] = g; p[2] = r; p[3] = 0xff;
    } else if (fb->bpp == 3) {
        p[0] = b; p[1] = g; p[2] = r;
    } else if (fb->bpp == 2) {
        uint16_t v = (uint16_t)(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3));
        p[0] = v & 0xff; p[1] = (v >> 8) & 0xff;
    }
}

static void fill_rect(FB *fb, int x, int y, int w, int h, uint8_t r, uint8_t g, uint8_t b) {
    for (int yy = y; yy < y + h; yy++) {
        for (int xx = x; xx < x + w; xx++) put_px(fb, xx, yy, r, g, b);
    }
}

static void draw_border(FB *fb, int x, int y, int w, int h, int t, uint8_t r, uint8_t g, uint8_t b) {
    fill_rect(fb, x, y, w, t, r, g, b);
    fill_rect(fb, x, y + h - t, w, t, r, g, b);
    fill_rect(fb, x, y, t, h, r, g, b);
    fill_rect(fb, x + w - t, y, t, h, r, g, b);
}

/* Tiny 5x7 bitmap font for needed chars */
typedef struct { char c; uint8_t row[7]; } Glyph;
static const Glyph font[] = {
    {' ', {0,0,0,0,0,0,0}},
    {'H', {0x11,0x11,0x11,0x1F,0x11,0x11,0x11}},
    {'E', {0x1F,0x10,0x10,0x1E,0x10,0x10,0x1F}},
    {'L', {0x10,0x10,0x10,0x10,0x10,0x10,0x1F}},
    {'O', {0x0E,0x11,0x11,0x11,0x11,0x11,0x0E}},
    {'W', {0x11,0x11,0x11,0x15,0x15,0x15,0x0A}},
    {'R', {0x1E,0x11,0x11,0x1E,0x14,0x12,0x11}},
    {'D', {0x1E,0x11,0x11,0x11,0x11,0x11,0x1E}},
    {'G', {0x0E,0x11,0x10,0x17,0x11,0x11,0x0F}},
    {'U', {0x11,0x11,0x11,0x11,0x11,0x11,0x0E}},
    {'I', {0x0E,0x04,0x04,0x04,0x04,0x04,0x0E}},
    {'M', {0x11,0x1B,0x15,0x15,0x11,0x11,0x11}},
    {'B', {0x1E,0x11,0x11,0x1E,0x11,0x11,0x1E}},
    {'2', {0x0E,0x11,0x01,0x02,0x04,0x08,0x1F}},
    {'3', {0x1E,0x01,0x01,0x0E,0x01,0x01,0x1E}},
    {'0', {0x0E,0x11,0x13,0x15,0x19,0x11,0x0E}},
    {'T', {0x1F,0x04,0x04,0x04,0x04,0x04,0x04}},
    {'S', {0x0F,0x10,0x10,0x0E,0x01,0x01,0x1E}},
    {'P', {0x1E,0x11,0x11,0x1E,0x10,0x10,0x10}},
    {'N', {0x11,0x19,0x15,0x13,0x11,0x11,0x11}},
    {'A', {0x0E,0x11,0x11,0x1F,0x11,0x11,0x11}},
    {'Y', {0x11,0x11,0x0A,0x04,0x04,0x04,0x04}},
    {'K', {0x11,0x12,0x14,0x18,0x14,0x12,0x11}},
    {'C', {0x0E,0x11,0x10,0x10,0x10,0x11,0x0E}},
    {'V', {0x11,0x11,0x11,0x11,0x11,0x0A,0x04}},
    {'1', {0x04,0x0C,0x04,0x04,0x04,0x04,0x0E}},
    {'4', {0x02,0x06,0x0A,0x12,0x1F,0x02,0x02}},
    {'5', {0x1F,0x10,0x1E,0x01,0x01,0x11,0x0E}},
    {'6', {0x06,0x08,0x10,0x1E,0x11,0x11,0x0E}},
    {'7', {0x1F,0x01,0x02,0x04,0x08,0x08,0x08}},
    {'8', {0x0E,0x11,0x11,0x0E,0x11,0x11,0x0E}},
    {'9', {0x0E,0x11,0x11,0x0F,0x01,0x02,0x0C}},
    {':', {0,0x04,0,0,0x04,0,0}},
    {'-', {0,0,0,0x1F,0,0,0}},
    {'!', {0x04,0x04,0x04,0x04,0x04,0,0x04}},
    {'.', {0,0,0,0,0,0,0x04}},
    {'+', {0,0x04,0x04,0x1F,0x04,0x04,0}},
    {0,{0}}
};

static const uint8_t *glyph_for(char c) {
    if (c >= 'a' && c <= 'z') c = (char)(c - 'a' + 'A');
    for (int i = 0; font[i].c; i++) if (font[i].c == c) return font[i].row;
    for (int i = 0; font[i].c; i++) if (font[i].c == ' ') return font[i].row;
    return font[0].row;
}

static void draw_text(FB *fb, int x, int y, int scale, const char *s, uint8_t r, uint8_t g, uint8_t b) {
    int cx = x;
    for (; *s; s++) {
        const uint8_t *rows = glyph_for(*s);
        for (int ry = 0; ry < 7; ry++) {
            for (int rx = 0; rx < 5; rx++) {
                if (rows[ry] & (1 << (4 - rx))) {
                    fill_rect(fb, cx + rx * scale, y + ry * scale, scale, scale, r, g, b);
                }
            }
        }
        cx += 6 * scale;
    }
}

static int set_raw(int fd) {
    struct termios tio;
    if (tcgetattr(fd, &tio) != 0) return -1;
    cfmakeraw(&tio);
    tio.c_cc[VMIN] = 0;
    tio.c_cc[VTIME] = 0;
    if (tcsetattr(fd, TCSANOW, &tio) != 0) return -1;
    return 0;
}

static long now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000L + ts.tv_nsec / 1000000L;
}

int main(void) {
    const char *fbdev = getenv("FRAMEBUFFER"); if (!fbdev) fbdev = "/dev/fb0";
    FB fb; memset(&fb, 0, sizeof(fb));
    fb.fd = open(fbdev, O_RDWR);
    if (fb.fd < 0) { perror("[gui-hello] open fb"); return 1; }

    struct fb_var_screeninfo v; struct fb_fix_screeninfo f;
    if (ioctl(fb.fd, FBIOGET_VSCREENINFO, &v) || ioctl(fb.fd, FBIOGET_FSCREENINFO, &f)) {
        perror("[gui-hello] fb ioctl"); return 1;
    }
    fb.w = v.xres; fb.h = v.yres; fb.bpp = v.bits_per_pixel / 8; fb.stride = f.line_length;
    fb.smem_len = f.smem_len;
    fb.fb = mmap(0, f.smem_len, PROT_READ|PROT_WRITE, MAP_SHARED, fb.fd, 0);
    if (fb.fb == MAP_FAILED) { perror("[gui-hello] mmap"); return 1; }
    fb.base = (long)v.yoffset * fb.stride + (long)v.xoffset * fb.bpp;

    fprintf(stderr, "[gui-hello] fb %dx%d %dbpp stride=%d base=%ld\n", fb.w, fb.h, v.bits_per_pixel, fb.stride, fb.base);

    int ttyfd = open("/dev/ttyS2", O_RDONLY | O_NONBLOCK);
    int gpiofd = open("/dev/ntgpio", O_RDONLY | O_NONBLOCK);
    if (ttyfd >= 0) set_raw(ttyfd); else perror("[gui-hello] open /dev/ttyS2");
    if (gpiofd < 0) perror("[gui-hello] open /dev/ntgpio");

    signal(SIGINT, on_sig);
    signal(SIGTERM, on_sig);

    int flash[4] = {0,0,0,0};
    long flash_until[4] = {0,0,0,0};
    long last_any = 0;
    unsigned char last_bytes[16]; int last_n = 0; char last_src[16] = "-";
    unsigned long total = 0;

    while (g_run) {
        long t = now_ms();
        /* draw UI */
        fill_rect(&fb, 0, 0, fb.w, fb.h, 12, 18, 28);
        draw_text(&fb, 60, 60, 8, "HELLO WORLD", 240, 240, 240);
        draw_text(&fb, 60, 140, 4, "MB230 GUI TEST - REMOTE INPUT", 120, 200, 255);
        draw_text(&fb, 60, 200, 3, "PRESS ANY REMOTE BUTTON", 200, 200, 120);

        const char *labels[4] = {"BTN 1", "BTN 2", "BTN 3", "BTN 4"};
        int bx = 60, by = 320, bw = 260, bh = 140, gap = 40;
        for (int i = 0; i < 4; i++) {
            int x = bx + i * (bw + gap);
            int active = (t < flash_until[i]);
            fill_rect(&fb, x, by, bw, bh, active ? 40 : 30, active ? 180 : 60, active ? 80 : 90);
            draw_border(&fb, x, by, bw, bh, 6, 230, 230, 230);
            draw_text(&fb, x + 40, by + 50, 5, labels[i], 255, 255, 255);
        }

        char line[64];
        snprintf(line, sizeof(line), "EVENTS: %lu", total);
        draw_text(&fb, 60, 520, 4, line, 255, 220, 120);
        snprintf(line, sizeof(line), "LAST SRC: %s", last_src);
        draw_text(&fb, 60, 580, 3, line, 180, 220, 180);
        if (last_n > 0) {
            char hex[80] = "LAST: ";
            int off = 6;
            for (int i = 0; i < last_n && i < 8 && off < (int)sizeof(hex)-4; i++) {
                off += snprintf(hex + off, sizeof(hex)-off, "%02X ", last_bytes[i]);
            }
            draw_text(&fb, 60, 620, 3, hex, 180, 220, 180);
        }
        if (t - last_any < 1200) {
            draw_text(&fb, 60, 680, 4, "INPUT RECEIVED!", 80, 255, 120);
        } else {
            draw_text(&fb, 60, 680, 4, "WAITING FOR INPUT...", 180, 180, 180);
        }
        draw_text(&fb, 60, fb.h - 60, 2, "CTRL-C TO EXIT - RUN VIA TELNET SHELL", 160, 160, 160);

        /* poll inputs */
        fd_set rfds; FD_ZERO(&rfds);
        int maxfd = -1;
        if (ttyfd >= 0) { FD_SET(ttyfd, &rfds); if (ttyfd > maxfd) maxfd = ttyfd; }
        if (gpiofd >= 0) { FD_SET(gpiofd, &rfds); if (gpiofd > maxfd) maxfd = gpiofd; }
        struct timeval tv; tv.tv_sec = 0; tv.tv_usec = 100000; /* 100ms */
        if (maxfd >= 0 && select(maxfd + 1, &rfds, NULL, NULL, &tv) > 0) {
            unsigned char buf[64];
            if (ttyfd >= 0 && FD_ISSET(ttyfd, &rfds)) {
                int n = read(ttyfd, buf, sizeof(buf));
                if (n > 0) {
                    total++; last_any = now_ms(); last_n = n < 16 ? n : 16; memcpy(last_bytes, buf, last_n);
                    snprintf(last_src, sizeof(last_src), "TTYS2");
                    int idx = (int)(total % 4);
                    flash_until[idx] = last_any + 500;
                    fprintf(stderr, "[gui-hello] ttyS2 %d bytes:", n);
                    for (int i = 0; i < n; i++) fprintf(stderr, " %02x", buf[i]);
                    fprintf(stderr, "\n");
                }
            }
            if (gpiofd >= 0 && FD_ISSET(gpiofd, &rfds)) {
                int n = read(gpiofd, buf, sizeof(buf));
                if (n > 0) {
                    total++; last_any = now_ms(); last_n = n < 16 ? n : 16; memcpy(last_bytes, buf, last_n);
                    snprintf(last_src, sizeof(last_src), "GPIO");
                    int idx = (int)(total % 4);
                    flash_until[idx] = last_any + 500;
                    fprintf(stderr, "[gui-hello] ntgpio %d bytes:", n);
                    for (int i = 0; i < n; i++) fprintf(stderr, " %02x", buf[i]);
                    fprintf(stderr, "\n");
                }
            }
        }
    }

    if (ttyfd >= 0) close(ttyfd);
    if (gpiofd >= 0) close(gpiofd);
    munmap(fb.fb, fb.smem_len);
    close(fb.fd);
    fprintf(stderr, "[gui-hello] exit\n");
    return 0;
}
