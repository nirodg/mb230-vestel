/*
 * opentv_payload.c — OpenTV payload v3.1 for the Vestel 17MB230 debug
 * launch path (RESEARCH ONLY — own hardware).
 *
 * Replaces the stock idtv app as the debug-ini program (ap0
 * nvt.app.debug.ini: program=/conf/opentv_payload). appmgr execvp()s it
 * directly, exactly like the stock aurora.elf — no shell, no wget, no
 * PATH dependence. The binary itself lives in the /conf volume (rw
 * ubifs, no noexec), so payload iterations only need a fast conf write.
 *
 * Facts established by analysis (see ARCHITECTURE.md rounds 7–9):
 *   - appmgr runs children as ROOT (enableMultiuser=n skips setuid/caps)
 *   - child stdout+stderr -> /tmp/stdout.all (tmpfs, lost each boot)
 *   - no IPC registration required; a child that exits gets relaunched
 *     by appmgr every ~30 s (the observed "boot loop"), so: NEVER exit.
 *   - the ap0 factory revert during the v2.1 session has exactly one
 *     remaining source: the TV's own update machinery downloading from
 *     the internet (aurora.elf strings: oadWriteFlashAndReboot,
 *     rootfs_burn.img, "web search for forced software update and burn
 *     flash"). No local 154 MB source exists (buffer volume provably
 *     empty, fs0 rootfs 5.8 MB, ap1 assets-only).
 *
 * Duties, in order:
 *   1. Log identity + full environment to /conf/opentv_payload.log
 *      (persistent; readable via the U-Boot probe .scr) and /tmp copy.
 *   2. Baseline the ap0 + nvt_sign UBI volumes (fingerprint trap).
 *   3. Snapshot appmgr's own boot log (/tmp/stdout.all) into /conf.
 *   4. Try to open a hardware watchdog (informational; pet if opened).
 *   5. Bring up eth0: insmod ntkethmac.ko, forced MAC, udhcpc, with a
 *      static-IP fallback if no lease.
 *   6. Internet block: `route del default` — kills the TV's OTA
 *      download path (the last revert source); LAN + telnet unaffected.
 *   7. Start busybox telnetd on :23 (-l /bin/sh = root shell).
 *   8. Diagnostics: TV's own wget to the PC (LAN reachability, no
 *      default route needed) and to 8.8.8.8 (must FAIL — proves the
 *      internet block holds).
 *   9. Loop forever: pet watchdog, re-del the default route every 30 s
 *      (run_aurora.sh's udhcpc renewals re-add it), re-check the ap0/
 *      nvt_sign fingerprints, re-arm telnetd, heartbeat.
 *
 * Build (static — no TV glibc dependency):
 *   docker run --rm --network host -v "$PWD":/w -w /w \
 *     arm32v7/ubuntu:16.04 \
 *     sh -c 'gcc -O2 -marm -mfloat-abi=hard -static opentv_payload.c \
 *            -o opentv_payload && strip opentv_payload'
 */

#include <errno.h>
#include <fcntl.h>
#include <net/if.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/utsname.h>
#include <time.h>
#include <unistd.h>

static FILE *lg_conf;   /* /conf/opentv_payload.log  — persists across boots */
static FILE *lg_tmp;    /* /tmp/opentv_payload.log   — this boot only      */

static void vlog(const char *tag, const char *fmt, ...)
{
    char msg[512];
    va_list ap;
    struct timespec ts;
    long long sec;
    long ms;

    va_start(ap, fmt);
    vsnprintf(msg, sizeof(msg), fmt, ap);
    va_end(ap);

    clock_gettime(CLOCK_REALTIME, &ts);
    sec = (long long)ts.tv_sec;
    ms = ts.tv_nsec / 1000000;

    if (lg_conf) { fprintf(lg_conf, "[%lld.%03ld] %s: %s\n", sec, ms, tag, msg); fflush(lg_conf); }
    if (lg_tmp)  { fprintf(lg_tmp,  "[%lld.%03ld] %s: %s\n", sec, ms, tag, msg); fflush(lg_tmp); }
}

/* system() wrapper that logs the command and its exit status */
static void run(const char *tag, const char *cmd)
{
    int rc;

    vlog(tag, "exec: %s", cmd);
    rc = system(cmd);
    if (rc == -1)
        vlog(tag, "system() failed errno=%d", errno);
    else
        vlog(tag, "rc=%d", rc);
}

static int eth0_has_ip(void)
{
    struct ifreq ifr;
    int s, ok;

    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, "eth0", IFNAMSIZ);
    s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s < 0)
        return 0;
    ok = (ioctl(s, SIOCGIFADDR, &ifr) == 0);
    close(s);
    return ok;
}

/* ---- round-9: ap0 / nvt_sign fingerprint trap -------------------------- *
 * The ap0 revert (factory bytes restored during the v2.1 session) was
 * never caught in the act. Baseline the ap0 and nvt_sign UBI volumes
 * through their char devices at boot, re-check every 30 s, and on ANY
 * change dump process state to /conf/opentv_revert.log (plus a ps
 * snapshot) so the reverter is caught red-handed. Node naming varies
 * by BSP: try the named aliases plus plain ubi0_<id>; whatever opens
 * and reads is baselined, and the log records every node's CRC so the
 * mapping is known afterwards. Expected prefixes: ap0 v3 = 0x134f25b
 * (256 KiB, matches the U-Boot probes), nvt_sign = 0x29d846a8 (package
 * volume image). A baseline taken before the reverter runs brackets
 * the U-Boot write-time CRC read-back (0xddfb3864) tightly.
 * ----------------------------------------------------------------------- */
struct trap {
    const char   *node;
    int           fd;
    unsigned long crc;
    long          len;
    int           live;   /* node opened and read OK */
};

static struct trap traps[] = {
    { "/dev/ubi0_ap0",      -1, 0, 0, 0 },
    { "/dev/ubi0_nvt_sign", -1, 0, 0, 0 },
    { "/dev/ubi0_0",        -1, 0, 0, 0 },
    { "/dev/ubi0_1",        -1, 0, 0, 0 },
    { "/dev/ubi0_2",        -1, 0, 0, 0 },
    { "/dev/ubi0_3",        -1, 0, 0, 0 },
};
#define TRAPS_N   (sizeof(traps) / sizeof(traps[0]))
#define TRAP_LEN  0x40000       /* 256 KiB prefix, as in the U-Boot probes */

static unsigned char trap_buf[TRAP_LEN];

static unsigned long crc32_buf(const unsigned char *p, long n)
{
    unsigned long c = 0xffffffffUL;
    long i;
    int k;

    for (i = 0; i < n; i++) {
        c ^= p[i];
        for (k = 0; k < 8; k++)
            c = (c >> 1) ^ (0xedb88320UL & (0UL - (c & 1)));
    }
    return ~c & 0xffffffffUL;
}

static long trap_read(struct trap *t, unsigned long *crc_out)
{
    long n;

    lseek(t->fd, 0, SEEK_SET);
    n = read(t->fd, trap_buf, TRAP_LEN);
    if (n <= 0)
        return n;
    *crc_out = crc32_buf(trap_buf, n);
    return n;
}

static void trap_init(void)
{
    unsigned long c;
    struct trap *t;
    long n;

    for (t = traps; t < traps + TRAPS_N; t++) {
        t->fd = open(t->node, O_RDONLY);
        if (t->fd < 0)
            continue;
        n = trap_read(t, &c);
        if (n <= 0) {
            vlog("TRAP", "%s opened but read failed errno=%d", t->node, errno);
            close(t->fd);
            t->fd = -1;
            continue;
        }
        t->len = n;
        t->crc = c;
        t->live = 1;
        vlog("TRAP", "%s len=%ld crc=0x%08lx (baseline)", t->node, n, c);
        if (c == 0x0134f25bUL)
            vlog("TRAP", "%s == v3 ap0 prefix (0x134f25b) — this is ap0",
                 t->node);
        else if (c == 0x29d846a8UL)
            vlog("TRAP", "%s == package nvt_sign volume", t->node);
    }
}

static void trap_check(void)
{
    unsigned long c;
    struct trap *t;
    long n;
    char cmd[768];

    for (t = traps; t < traps + TRAPS_N; t++) {
        if (!t->live)
            continue;
        n = trap_read(t, &c);
        if (n <= 0) {
            vlog("TRAP", "%s read failed errno=%d", t->node, errno);
            continue;
        }
        if (n != t->len)
            vlog("TRAP", "%s LENGTH CHANGED %ld -> %ld", t->node, t->len, n);
        if (c == t->crc)
            continue;
        vlog("TRAP", "*** %s CHANGED 0x%08lx -> 0x%08lx — dumping state ***",
             t->node, t->crc, c);
        snprintf(cmd, sizeof(cmd),
            "{ echo '=== %s changed crc 0x%08lx -> 0x%08lx';"
            "date;"
            "echo '-- ps:';"
            "ps w;"
            "echo '-- /proc cmdlines:';"
            "for d in /proc/[0-9]*; do"
            "  printf '%%s ' \"$d\";"
            "  tr '\\0' ' ' < $d/cmdline 2>/dev/null;"
            "  echo;"
            "done; } >> /conf/opentv_revert.log 2>&1",
            t->node, t->crc, c);
        run("TRAP", cmd);
        t->crc = c;             /* report each change once */
    }
}

int main(int argc, char **argv, char **envp)
{
    struct utsname u;
    int wd = -1, i;
    char **e;
    int a;

    lg_conf = fopen("/conf/opentv_payload.log", "a");
    lg_tmp = fopen("/tmp/opentv_payload.log", "a");
    if (!lg_conf)
        vlog("BOOT", "WARNING: /conf/opentv_payload.log not opened errno=%d", errno);

    vlog("BOOT", "=== opentv payload v3.1 (route-block + ap0/nvt_sign trap) ===");
    uname(&u);
    vlog("BOOT", "kernel: %s %s %s", u.sysname, u.release, u.version);
    vlog("BOOT", "uid=%d euid=%d pid=%d ppid=%d", getuid(), geteuid(), getpid(), getppid());
    {
        char cwd[256];
        if (getcwd(cwd, sizeof(cwd)))
            vlog("BOOT", "cwd=%s", cwd);
    }
    for (a = 0; a < argc; a++)
        vlog("BOOT", "argv[%d]=%s", a, argv[a] ? argv[a] : "(null)");
    for (e = envp; e && *e; e++)
        vlog("ENV", "%s", *e);

    /* round-9 fingerprint trap: baseline ap0/nvt_sign before anything
     * else runs, so a later change is attributable */
    trap_init();

    /* snapshot appmgr's own boot log into /conf (post-mortem evidence) */
    run("COPY", "cp /tmp/stdout.all /conf/opentv_stdout_boot.log 2>/dev/null");
    run("COPY", "cp /tmp/appmgr.log /conf/opentv_appmgr_boot.log 2>/dev/null");

    /* watchdog: informational only — try to open, pet if it exists */
    wd = open("/dev/watchdog", O_WRONLY);
    if (wd < 0)
        wd = open("/dev/watchdog0", O_WRONLY);
    if (wd >= 0)
        vlog("WD", "watchdog opened fd=%d — will pet every 10 s", wd);
    else
        vlog("WD", "no watchdog node (errno=%d) — nothing to pet", errno);

    /* network bring-up (mirrors the stock script, proven values) */
    run("NET", "insmod /vendor/modules/ntkethmac.ko");
    run("NET", "ifconfig eth0 down");
    run("NET", "ifconfig eth0 hw ether D4:E2:CC:EC:45:E9");
    run("NET", "ifconfig eth0 up");
    run("NET", "udhcpc -s /etc/udhcpc/default.script eth0");
    if (!eth0_has_ip()) {
        vlog("NET", "no DHCP lease — applying static fallback 192.168.0.240/24");
        run("NET", "ifconfig eth0 192.168.0.240 netmask 255.255.255.0 up");
    } else {
        vlog("NET", "eth0 has an address");
    }

    /* v3 mitigation: kill the default route. The TV's only remaining
     * ap0-revert source is its own update machinery fetching from the
     * internet; without a default route it cannot. LAN (PC, CIFS,
     * telnet) is same-subnet and unaffected. busybox on this rootfs has
     * no `ip` applet — `route` only. run_aurora.sh's udhcpc renewals
     * re-add the route, so this is re-asserted every 30 s below. */
    run("BLOCK", "route del default");
    run("ROUTE", "route -n >>/conf/opentv_payload.log 2>&1");

    /* root shell over telnet */
    run("SVC", "/usr/sbin/telnetd -l /bin/sh -p 23");

    /* one-shot diagnostics: (a) the TV's own busybox wget against the PC
       — proves LAN reachability without a default route; (b) an internet
       fetch that MUST fail with a network-unreachable error — proves
       the route block holds. Output (incl. errors) to /conf/wget_test.log. */
    run("DIAG",
        "/usr/bin/wget -O /tmp/wget_test.bin http://192.168.0.100:8123/aurora.elf"
        " >>/conf/wget_test.log 2>&1");
    run("DIAG",
        "/usr/bin/wget -T 5 -O /dev/null http://8.8.8.8/"
        " >>/conf/wget_test.log 2>&1");

    /* never exit: appmgr would relaunch us in a loop (and an armed hw
       watchdog would bite). Pet + re-arm + heartbeat. */
    for (i = 0; ; i++) {
        sleep(10);
        if (wd >= 0 && write(wd, "1", 1) < 0) {
            vlog("WD", "pet failed errno=%d — closing", errno);
            close(wd);
            wd = -1;
        }
        if (i % 3 == 2) {   /* every 30 s */
            /* undo any default route re-added by udhcpc renewals in the
             * looping run_aurora.sh (remote.txt stays, per round 9) */
            run("BLOCK", "route del default 2>/dev/null");
            trap_check();
        }
        if (i % 6 == 5)     /* every 60 s: harmless EADDRINUSE if running */
            run("SVC", "/usr/sbin/telnetd -l /bin/sh -p 23");
        if (i % 180 == 179) /* every 30 min heartbeat */
            vlog("ALIVE", "still running");
    }
}
