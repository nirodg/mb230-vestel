# MB230 (Vestel/Novatek) Reverse Engineering — Findings

**Target:** Horizon 50HL7530U/B (Vestel 17MB230 mainboard, Novatek NT72671 SoC)
**Firmware:** Kylo `V.0.51.52.3` (SVN 379809, build 2025-11-25)
**Panel:** `50_VESQNDTN41J2D_UHD_D_XDF0_V_230_XX` (VES500QNDT-N41-2D, Inolux, 3840×2160)
**Method:** Non-invasive USB dump via service menu
**Date:** 2026-10

---

## Table of Contents

- [MB230 (Vestel/Novatek) Reverse Engineering — Findings](#mb230-vestelnovatek-reverse-engineering--findings)
  - [Table of Contents](#table-of-contents)
  - [Executive Summary](#executive-summary)
  - [Platform Overview](#platform-overview)
    - [Confirmed Behaviour](#confirmed-behaviour)
    - [Confirmed Upload Folders](#confirmed-upload-folders)
    - [USB Stick Requirements](#usb-stick-requirements)
  - [The EFSL Profile Format](#the-efsl-profile-format)
    - [File Header (32 bytes)](#file-header-32-bytes)
    - [Known Type Codes](#known-type-codes)
    - [Entry Data Section](#entry-data-section)
    - [Sample Strings Found in `mb230_hwprofile.bin`](#sample-strings-found-in-mb230_hwprofilebin)
  - [The Language Profile](#the-language-profile)
    - [Structure](#structure)

---

## Executive Summary

The MB230 is a **Linux-based embedded TV platform** built on the Novatek NT72671 SoC. Despite appearing locked down (secure boot, read-only `/vendor/`, no shell access), the **service menu exposes a "USB Operations" function** that provides bidirectional file transfer between the TV and a FAT32 USB stick.

By placing specific folders (`DownloadProfile.MB230`, `DownloadPq.MB230`, `DownloadSpi.MB230`) on a USB stick and triggering USB Operations, **the TV dumps its internal configuration** — hardware/software profiles, panel timing, EDID, audio calibration, HDCP credentials, and 5 MB of language strings — to the USB stick.

A second pass with the **same folders but different contents** lets the TV accept modified files back into `/conf/`, enabling:

- Panel timing adjustments (`ptf.ptf`)
- Picture quality tuning (`PCF.pcf`, `PQF.bin`)
- Audio calibration (`AQ.bin`, `DAP_SE_SetParam.txt`, etc.)
- Hardware/software profile replacement (`mb230_hwprofile.bin`, `mb230_swprofile.bin`)
- Boot logo replacement (`spi/boot_logo.bin`)

The **language profile (`mb230_langprofile.bin`) is NOT in the upload path** — it lives in read-only `/vendor/` and can only be dumped, not replaced.

The Cobalt (Chromium-based YouTube TV) application layer was also extracted from the firmware. Its `run.sh` reveals extensive debug modes and commented-out flags (`--remote_debugging_port`, `--debug_console=hud`) that would enable Chrome DevTools access if the launch script could be modified — which requires UART or a Cobalt bundle update, neither of which is exposed via USB.

**Primary remaining barrier:** the AWS S3 firmware update URL uses presigned signatures generated on the TV; the corresponding AWS secret key was not found in any extractable file. Live network capture of an update check remains the only way to obtain fresh URLs for the firmware partitions.

---

## Platform Overview

| Property | Value |
|----------|-------|
| Mainboard | Vestel 17MB230 |
| SoC | Novatek NT72671 |
| Architecture | ARM 32-bit (ELF32, hard-float, EABI v5) |
| OS | Linux (kernel + U-Boot + BusyBox) |
| Application framework | Cobalt (Chromium-based), "Picasso" UI |
| Bootloader | Kylo, version `MB230-0032` |
| Secure boot | Enabled (`[vhash] secure boot is 1:1`) |
| Languages | ~30 supported UI languages |
| Flash | SPI NOR (config) + NAND (rootfs, profiles) |
| Panel interface | LVDS (dual-pixel output for 4K) |
| HDMI | HDMI 2.0b (up to 4K@60, HDR10 + HLG) |

**The TV identifies itself to the network as:**

Model/Vestel-MB230 VSTVB MB200 HbbTV/1.5.1
(+DRM; HORIZON; MB230; 0.51.52.3; ; _TV_NT72671_2019;)

```

---

## The Service Menu USB Operations

### Access
MENU + 4 7 2 5 → Service Menu → USB Operations → OK

```

### Confirmed Behaviour

The `PerformUSBOperations` function of the TV firmware executes the following sequence when triggered (from `usb_trace` logs):
Update Boot Logo...
[reads /media/sdX/spi/boot_logo.bin if present]
Update Profile...
_CopyFile: cp -f /media/sdX/profile/mb230_hwprofile.bin /conf
_CopyFile: cp -f /media/sdX/profile/mb230_swprofile.bin /conf
_CopyFile: /media/sdX/profile/mb230_devprofile.bin is not exist!
Download Profile...
_CopyFile: cp -f /conf/mb230_hwprofile.bin /media/sdX
_CopyFile: cp -f /conf/mb230_swprofile.bin /media/sdX
_CopyFile: cp -f /vendor/mb230_langprofile.bin /media/sdX
Update AQ/PQ/Panel Files...
_CopyFile: cp -f /media/sdX/pq/PCF.pcf /conf
_CopyFile: cp -f /media/sdX/pq/PQF.bin /conf
_CopyFile: cp -f /media/sdX/pq/ptf.ptf /conf
_CopyFile: cp -f /media/sdX/sound/AQ.bin /conf
[...]
Download AQ/PQ/Panel Files...
_CopyFile: cp -f /conf/PCF.pcf /media/sdX
_CopyFile: cp -f /conf/PQF.bin /media/sdX
_CopyFile: cp -f /conf/ptf.ptf /media/sdX
[...]
Update ROFIX Files...
[reads hdcp/edid/credentials from USB and writes to SPI flash]
Download ROFIX Files...
#PLAT-ROFIX# BackupToFile: /media/sdX/mb230_hdcp.bin (326 bytes)
#PLAT-ROFIX# BackupToFile: /media/sdX/mb230_hdcp2.bin (918 bytes)
#PLAT-ROFIX# BackupToFile: /media/sdX/mb230_credentials.bin (7168 bytes)
#PLAT-ROFIX# BackupToFile: /media/sdX/mb230_mac.bin (32 bytes)

```

### The "Download" Folder Trigger

Creating the following empty folders on the USB stick changes the behaviour of `USB Operations` to perform the **Download** (TV → USB) steps:
/USB_ROOT/DownloadProfile.MB230/
/USB_ROOT/DownloadPq.MB230/
/USB_ROOT/DownloadSpi.MB230/

```

Without these folders, only the **Update** (USB → TV) steps run.

### Confirmed Upload Folders

To push files **into** the TV, use **lowercase** folder names:

| Folder | Files Accepted |
|--------|----------------|
| `profile/` | `mb230_hwprofile.bin`, `mb230_swprofile.bin`, `mb230_devprofile.bin` |
| `pq/` | `PCF.pcf`, `PQF.bin`, `ptf.ptf`, `dolby.bin`, `Dolby.cfg`, `tcon.bin` |
| `sound/` | `AQ.bin`, `DAP_SE_SetParam.txt`, `DAPV2_SE_SetParam.txt`, `DTS_VX_AQ.bin`, `subw_config_file.txt`, `ad82586c_config_file.txt` |
| `spi/` | `boot_logo.bin` |

**Folder names are case-sensitive.** `Profile/` will not work; `profile/` will.

### USB Stick Requirements

- **FAT32** formatted
- **USB 2.0** preferred (USB 3.0 may have driver issues)
- **8 GB or larger** recommended

---

## The EFSL Profile Format

`mb230_hwprofile.bin` and `mb230_swprofile.bin` use a custom Novatek container format called **EFSL**.

### File Header (32 bytes)
Offset Size Field Description

0x00 4 magic "EFSL" (0x4546534C)
0x04 4 version uint32 LE (currently 1)
0x08 4 declared_size uint32 LE (reserved allocation size)
0x0C 4 reserved 0xFFFFFFFF (unused marker)
0x10 16 profile_type ASCII null-padded: "hwprofile", "swprofile"
0x20 ... entry table sequence of 20-byte entries

```

**Note:** `declared_size` is a **maximum allocation**, not the actual file size. The HW profile declares 40,511 bytes but the actual file on the TV is 25,875 bytes. The SW profile declares 91,831 bytes but actual is 60,484 bytes. The difference represents reserved space for factory entries that are not populated on consumer units.

### Entry Format (20 bytes)
Offset Size Field Description

+0x00 4 type uint32 LE (entry type code)
+0x04 4 subtype uint32 LE (entry sub-type / flags)
+0x08 4 value uint32 LE (scalar value, for numeric entries)
+0x0C 4 data_offset uint32 LE (offset in the FULL profile)
+0x10 4 crc32 uint32 LE (CRC32 of the entry's data)

```

The entry table is **terminated by a 20-byte all-zero entry**.

### Known Type Codes

| Type | Meaning |
|------|---------|
| `0x00000000` | Root / terminator |
| `0x00000100` | Generic |
| `0x00000105` | String (most common — 117+ occurrences) |
| `0x00000200` | Numeric |
| `0x00000205` | String (v2) |
| `0x00000300` | Numeric setting |
| `0x00000500` | Setting |
| `0x00000502` | Numeric setting |
| `0x00000503` | Numeric setting (v2) |
| `0x00000600` | Binary blob |

### Entry Data Section

The data section lives **after the entry table**, starting at the offset declared in entry 0's `data_offset` field. In the HW profile it starts at `0x646C` (25,708).

Data is stored as **null-terminated UTF-8 strings** for string entries, and as binary blobs for other types.

### Sample Strings Found in `mb230_hwprofile.bin`
10Watt
Surround Sound
TIGroup13
default.aqs.bin
Default
SingleTact
This line will be filled by production!
RCA_43XX_RC5
Si2157
VRc48XX

```

These correspond to speaker configuration, audio mode, tuner type, remote control type, local key type, etc.

### Sample Strings Found in `mb230_swprofile.bin`
Vestel TV
NETWORK_ONE
HORIZON
VESTEL
Movie Sense
Vestel Pixellence
7704.dcf
0009df
s3-eu-west-1.amazonaws.com/vstlupdate
SERVER_HTTP_SECURE_TYPE
17MB230
vstl.1973

```

These reveal the update server path and feature flags.

---

## The Language Profile

`mb230_langprofile.bin` (~5 MB) contains the UI translation strings for ~30 languages.

### Structure

The file is a **packed null-terminated UTF-8 string table** with a repeating block structure:
[Key 1 in English]\0
[Key 1 in Albanian]\0
[Key 1 in Khmer]\0
[Key 1 in Azerbaijani]\0
...
[Key 1 in Last Language]\0
[Key 2 in English]\0
[Key 2 in Albanian]\0
...

```

For each UI string key, all translations are stored **back-to-back**, separated only by null terminators. There are no length prefixes and no offset table in the sections we examined.

### Languages Observed (in order)

English, Albanian, Khmer, Azerbaijani, Ukrainian, Croatian, Czech, Danish, Dutch, Estonian, Finnish, French, German, Irish, Greek, Hebrew, Hungarian, Italian, Kazakh, Latvian, ... (~30 total)

### Known Offsets

| Offset | String |
|--------|--------|
| `0x0BE868` (780,392) | `Welcome please select your language!` |
| `0x0BE9AD` (780,973) | `Welcome please select your language!` (second language) |
| `0x102669` (1,058,665) | `Welcome!` |
| `0x164F63` (1,462,371) | `Welcome Screen` |

### Modification Feasibility

**The language profile cannot be uploaded via USB.** The `PerformUSBOperations` upload section does not check for `langprofile.bin`. It lives in `/vendor/`, which is a read-only squashfs or similar. Modifying it requires UART shell access or a full firmware reflash.

---

## Panel Timing File (`ptf.ptf`)

A **plain ``` INI-style file** that configures the panel timing generator. This is the **most modifiable** file in the dump — ``` format, uploadable via USB.

### Key Fields

```ini
u8PanelID            = 255           # 0xFF = generic
b8Mode50Hz           = 1             # 50 Hz mode enabled
au8Name              = VX1_Direct    # Novatek VX1 LVDS timing generator
b8DualPixelOutput    = 1             # Required for 4K
enLvdsFormat         = 1             # LVDS interface
u16VX1PreEmphasisG1  = 5             # LVDS pre-emphasis
u16VX1SwingG1        = 18            # LVDS swing
u16PanelPowerOnDelay1 = 30           # ms
u16PanelPowerOnDelay2 = 2800         # ms — for LVDS lock
u16BackLightLevel    = 100           # 0-100
u16BacklightFreq     = 10000         # 10 kHz PWM
Revision             = $Rev: 296595 $
50 Hz Timing
ini
stMode50Hz.u16Width          = 3840
stMode50Hz.u16Height         = 2160
stMode50Hz.u16TypHTotal      = 4800
stMode50Hz.u16TypVTotal      = 2475
stMode50Hz.u16PLL            = 59400   # 594 MHz
60 Hz Timing
ini
stMode60Hz.u16Width          = 3840
stMode60Hz.u16Height         = 2160
stMode60Hz.u16TypHTotal      = 4400
stMode60Hz.u16TypVTotal      = 2250
stMode60Hz.u16PLL            = 59400   # 594 MHz
Computed pixel clock: 4800 × 2475 × 50 Hz = 594 MHz ✅ (matches EDID)

Fields Considered Safe to Modify
u16BackLightLevel (default brightness)

u16BacklightFreq (PWM frequency)

u16PanelPowerOnDelay1/2 (boot timing)

b8Mode50Hz (enable/disable 50 Hz)

u8DitheringBit (8→10 bit dithering)

Fields to Leave Alone
stMode*.u16TypHTotal, u16TypVTotal, u16PLL — panel timing

u16PanelPowerGPIO, u16PanelBackLightGPIO — GPIO pin assignments

u16LVDSPhase* — clock phase

The Revision = $Rev: 296595 $ line must remain at the end of the file (noted in the file itself).

EDID Files
Four EDID variants were dumped:

File	Purpose
edid.edid	HDMI 2.0 full (600 MHz TMDS, includes HDMI Forum VSDB)
edid14.edid	HDMI 1.4 fallback (300 MHz TMDS)
edid20v.edid	HDMI 2.0 variant
edid.vga	Analog VGA (1920×1080 @ 60)
Common Properties
Property	Value
Manufacturer	VES (Vestel)
Product Code	0x3700
Manufactured	Week 1 of 2019
Monitor Name	50UHD_LCD_TV
Native Resolution	3840×2160 @ 60 Hz
Gamma	2.20
Color Space	RGB 4:4:4, YCbCr 4:4:4, YCbCr 4:2:2
HDR	HDR10 (SMPTE ST2084), HLG
Wide Color	BT.2020, xvYCC601/709
HDMI Audio Support
Linear PCM (2 ch)

AC-3 (6 ch)

DTS (8 ch)

Enhanced AC-3 / DD+ (8 ch)

DTS-HD (8 ch, up to 192 kHz)

Not supported: Dolby TrueHD, DTS-HD Master Audio, Dolby Vision.

VGA EDID
Analog VGA, 1920×1080 @ 60 Hz, 1360×768 @ 60 Hz, gamma 1.00, max dotclock 170 MHz.

The DCF Firmware Manifest
The file 7704.dcf (2.8 KB) is downloaded from AWS S3 during update checks and describes the firmware partition layout.

Structure
```
Target=/0009df/7704.dcf
Version=3355651
CodeSize=20000000
LangReason=eng:Test B&O update for model 0x0001
LangReason=fre:French B&O
LangReason=deu:German B&O
Permission=0
VersionRangeMin=0x000000ff
VersionRangeMax=0x00ffffff

Load=/0009df/images/part_1.bin
Address=0
Authentication=52da3d96df0c8cc5362fc997417f1a2e3b9b26955b6cc9d74e9f3fda527246b8
SourceStart=0
SourceEnd=19999999
SourceAuthentication=none
Target=0
[repeated for part_2 through part_11]
Partition Table
Part	Target Address	Source Size	SHA-256 (first 8 bytes)
part_1	0x00000000	20,000,000	52da3d96
part_2	0x20000000	20,000,000	21d33129
part_3	0x40000000	20,000,000	55d43b32
part_4	0x60000000	20,000,000	bdaae865
part_5	0x80000000	20,000,000	8b4f841b
part_6	0x100000000	20,000,000	45ba4cf4
part_7	0x120000000	20,000,000	3ce6db09
part_8	0x140000000	20,000,000	e198b06e
part_9	0x160000000	20,000,000	ebc0e54d
part_10	0x180000000	20,000,000	e2b71b4a
part_11	0x200000000	18,780,467	6ebc1002
Total firmware size: ~218 MB across 11 parts.

Each part is SHA-256 authenticated. The TV verifies the hash before flashing. Modifying a part requires recomputing its hash — which is possible — but the DCF itself is signed via the presigned URL, so a modified DCF will not be accepted.

AWS S3 Firmware Update Flow
Update URL Pattern
```
https://s3-eu-west-1.amazonaws.com/vstlupdate/MB230/{device_id}/ping.me
https://s3-eu-west-1.amazonaws.com/vstlupdate/MB230/{device_id}/0009df/7704.dcf
https://s3-eu-west-1.amazonaws.com/vstlupdate/MB230/{device_id}/0009df/images/part_N.bin
For this TV, device_id is 7704 (and variants 7704_001, 7704_002).

There is also a QA channel at qaupdate instead of vstlupdate.

Presigned URL Parameters
```
X-Amz-Algorithm=AWS4-HMAC-SHA256
X-Amz-Credential=AKIAITI4DYZ62MGPXX5A/YYYYMMDD/eu-west-1/s3/aws4_request
X-Amz-Date=YYYYMMDDTHHMMSSZ
X-Amz-Expires=86400
X-Amz-SignedHeaders=host
X-Amz-Signature=<HMAC-SHA256>
The Access Key ID
The AWS Access Key ID AKIAITI4DYZ62MGPXX5A is embedded in the firmware and appears in every presigned URL. The corresponding secret key was not found in any extracted file (searched: syslogs, usb_traces, EFSL profiles, Cobalt binary, extracted rootfs).

Obtaining Fresh URLs
The presigned URLs are only valid for 24 hours. To download firmware:

Capture live network traffic during an update check (reboot the TV with a packet capture running)

Extract the fresh URLs from the capture

Download each part via curl within the 24-hour window

Alternatively, if the AWS secret key could be extracted (requires UART shell access to the TV), the URLs could be regenerated on demand.

The Cobalt Application Layer
Cobalt is YouTube's Chromium-based application platform for embedded devices. The MB230 ships with a complete Cobalt bundle, extractable from the firmware dump.

Bundle Structure
```
cobalt/
├── cobalt                      # ELF32 ARM binary (9.7 MB .```, 2.5 MB .rodata)
├── content/
│   ├── data/
│   │   ├── fonts/              # Noto fonts for 50+ scripts
│   │   ├── icu/                # ICU 56 internationalization data
│   │   ├── ssl/                # System CA certificates
│   │   └── web/                # HTML/JS/CSS (Widevine GTS, etc.)
├── lib/
│   ├── libnvtaudio.so
│   ├── libnvtvideo.so
│   ├── libwidevine_ce_cdm_shared.so
│   └── libwvsrvapi.so
├── run.sh                      # Main launcher
├── run_nplb.sh                 # Alternate launcher
├── cobalt_env.sh               # OP_MODE / PERF_MODE
├── brand_name_env.sh           # BRAND_NAME="customer"
├── cache_env.sh                # COBALT_HOME="/mtd_rwarea"
├── lang_env.sh                 # Language mapping (reads /mtd_apdat/bcp47.txt)
├── systemproperty_env.sh       # Platform identity + S2T API key
├── update_cobalt_sp.sh         # Build script for update tarball
└── version.txt                 # b657ed56d5fa8fa9a72e050cb8ac4186068e90ed
The run.sh Modes
The launcher reads OP_MODE from cobalt_env.sh (default 1) and supports 15 modes:

Mode	Name	URL / Behavior
1	YouTubeTV	Default — YouTube TV app
2	YouTubeTVKid	https://www.youtube.com/tv/kids
3	2018YTCert	YouTube certification site
4	2018YTCertSSL	Cert test with SSL
5	YTBuringTest	Burn-in test
6	YoutubeTVwithUIMetrics	YouTube + UI metrics overlay
7	YouTubeTVPreCertTest	Pre-certification test
8	YTEnDuranceTest	Endurance test
9	YTSSLSecurityTest	Google cert-test sandbox
10	YoutubeWithDebugConsole	YouTube + on-screen JS console
11	YoutubeWithFPSDisplay	YouTube + FPS counter
12	B2QAutomation	Browse-to-Watch automation
13	YT2019PreTest	2019 cert suite
14	YT2019CobaltAppLifecycle	App lifecycle API
15	WidevineGTS_YT2019DemoPlayer	Local file: file:///widevine_gts/widevine_gts.html
Commented-Out Debug Flags
run.sh contains commented lines that, if uncommented, would enable powerful debug features:

bash
#REMOTE_DEBUGGING_PORT="--remote_debugging_port=9222"
#DEBUG_CONSOLE="--debug_console=hud"
#TRACE="--timed_trace=20 --timed_trace_log=on"
#MEMORY_TRACKER="--memory_tracker=allocation_logger"
#WEBUI="--csp_mode=disable --allow_http --partial_layout=on --ignore_certificate_errors"
Enabling --remote_debugging_port=9222 would expose Chrome DevTools Protocol on port 9222, giving full DOM inspection and JavaScript execution in the running browser.

This is not achievable via USB because:

The Cobalt bundle lives on a read-only partition

The USB Operations upload handler does not include Cobalt update files

The com.nvt.cobalt.{gold,qa}.tar.gz update mechanism is not exposed via USB

Platform Identity (systemproperty_env.sh)
bash
export FRIENDLY_NAME="VSTVB"
export PLATFORM_NAME="gles; MB230"
export CHIPSET_MODEL_NUMBER="NT72671"
export MODEL_NAME="MB230 SmartTV"
export MODEL_YEAR="2019"
export NETWORK_OPERATOR_NAME=""
export S2T_API_Key="AIzaZDy-wTWbRb6mxzForkuB1qDRYYvPeOnfflN"
The S2T_API_Key is a real Google Cloud API key embedded in the firmware for speech-to-``` (voice search).

Filesystem Layout
Reconstructed from syslog and usb_trace analysis.

```
/                          # Read-only root (squashfs, on NAND)
├── conf/                  # Writable configuration partition
│   ├── mb230_hwprofile.bin
│   ├── mb230_swprofile.bin
│   ├── PCF.pcf
│   ├── PQF.bin
│   ├── ptf.ptf
│   ├── AQ.bin
│   ├── DAP_SE_SetParam.txt
│   ├── DAPV2_SE_SetParam.txt
│   ├── DTS_VX_AQ.bin
│   ├── subw_config_file.txt
│   ├── ad82586c_config_file.txt
│   ├── dialsetting.ini
│   ├── fto.bin
│   └── power_up.txt
│
├── vendor/                # Read-only vendor partition
│   ├── mb230_langprofile.bin
│   ├── TA/                # Trusted Applications (DRM)
│   │   ├── nvtta.epkg
│   │   ├── nflx51.epkg
│   │   ├── marlin.epkg
│   │   ├── nvtsvppr30.epkg
│   │   ├── amzpv.epkg
│   │   ├── cip_ecp.epkg
│   │   ├── ta_nagra.epkg
│   │   └── kutils.epkg
│   ├── media_codecs.xml
│   ├── browser_dir/       # Opera browser
│   └── html_applications/ # Digital IB (Picasso UI)
│
├── buffer/                # RAM disk (tmpfs)
│   ├── logo.jpg           # Boot logo
│   ├── bootlogo.jpg
│   ├── conf_backup/
│   │   ├── mb230_swprofile.bin
│   │   ├── mb230_hwprofile.bin
│   │   └── ptf.ptf
│   ├── .cache/cobalt/     # Cobalt runtime cache
│   ├── browser_home/      # Browser cache
│   └── samba/
│
├── media/                 # Mount points
│   └── sda1/              # USB drive (auto-mounted)
│
├── tmp/                   # Temp files
│   └── xboot.bin          # Bootloader dump (from /dev/mtd0)
│
├── mtd_rwarea/            # Writable user data (Cobalt home)
├── mtd_apdat/             # Application data (bcp47.txt language config)
└── mtd_apexe/             # Application executables
    └── board/com.nvt.xpca/ProductionConfig.config.xml
MTD Partition Roles
Partition	Purpose
mtd_apexe	Application executables (read-only)
mtd_apdat	Application data (writable)
mtd_rwarea	Read-write user area (Cobalt $HOME)
/dev/mtd0	Bootloader (dumped to /tmp/xboot.bin)
SPI Flash Layout (from logs)
Address	Purpose
0x00000 – 0x80000	Bootloader (xboot)
0x20000	EDID block
0x23000	MAC / config block
0x30000	Boot parameters
0x40000	Kernel / firmware header
0x63ff0	TV lifetime counter
0x70e00 – 0x71000	Runtime config
Modification Paths
Verified Working via USB
Target	File	Folder	Notes
HW profile	mb230_hwprofile.bin	profile/	Copy to /conf/ confirmed
SW profile	mb230_swprofile.bin	profile/	Copy to /conf/ confirmed
Panel timing	ptf.ptf	pq/	``` file, copy confirmed
PQ config	PCF.pcf	pq/	Binary, copy confirmed
PQ factory	PQF.bin	pq/	Binary, copy confirmed
Audio	AQ.bin, DAP*.txt, etc.	sound/	Copy confirmed
Boot logo	boot_logo.bin	spi/	Format-sensitive (JPEG in .bin)
Confirmed NOT Supported via USB
Language profile (mb230_langprofile.bin) — lives in /vendor/, not in upload handler

Cobalt bundle — not exposed in PerformUSBOperations

Full firmware reflash — requires kylo_usb_update.bin mechanism, not service menu

EDID upload — backup only, no upload handler for edid*.edid

Requires UART
Direct filesystem read/write

Modify /vendor/ (language profile, Cobalt)

Extract AWS secret key

Enable Cobalt remote debugging (by modifying run.sh on disk)

Disable secure boot (not recommended)

Known Limitations
mb230_hwprofile.bin and mb230_swprofile.bin are truncated relative to the header's declared_size. This is normal — the declared size reserves space for factory entries that are not populated on consumer units.

The language profile cannot be modified via USB. It's read-only on the TV.

The AWS secret key is not extractable from the dump. Only the access key ID is present. Fresh firmware URLs require live network capture.

Secure boot is enabled. The bootloader and kernel are signature-verified. Only configuration data can be modified.

The EDID is backup-only. No upload path exists for HDMI configuration.

Cobalt's debug flags are compiled in but commented out. Enabling them requires modifying the Cobalt bundle, which is not exposed via USB.

devprofile.bin is referenced but not present. The TV checks for it during USB Operations. Its format is presumably identical to hwprofile/swprofile (EFSL).

The presigned AWS URLs are valid for 24 hours. Past that, they return 403 Forbidden.

Tooling
mb230_inspector.py
A Tkinter GUI for parsing and inspecting all dumped file types:

PTF viewer — decodes all timing parameters, computes pixel clock and refresh rate, colour-codes risk levels

EDID viewer — decodes base block, CTA-861 extension, HDMI VSDB, HDR metadata, checksum validation

EFSL viewer — 20-byte entry table, type names, CRC verification, extracted strings, raw hex

Language profile viewer — string table with filter, anchor-based language detection

XML viewer — collapsible tree + pretty-printed code + raw

``` viewer — plain ``` files

Binary viewer — PQ / Audio / Other files: summary + extracted strings + hex

Dependencies: None (uses only Python stdlib).