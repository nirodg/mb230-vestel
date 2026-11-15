# aurora.elf (stock MB230 idtv app) — static analysis

**Target:** `com.nvt.idtv/aurora.elf` (stock main TV application on Vestel/Novatek MB230 "Kylo")
**Analyzed binary:** extracted from `mb230-full-backup/mtd12_fs0.bin` → UBI volume `ap0` (SquashFS) → `com.nvt.idtv/aurora.elf`
**Local copy:** `/tmp/opencode/rea-targets/aurora_stock.elf` (working extraction for this session)
**Analysis date:** 2026-11-15
**Methods:** `file`, `readelf` (headers/sections/segments/dynamic/NEEDED), and `strings -n 6` (197,142 strings) + targeted searches. **REA MCP deep analysis (decompilation/pseudocode/callgraph) was not available in this session:** `open_binary` reached Hopper but timed out waiting for bridge readiness (`provider_timeout`, launcher showed plugin scan only; may require GUI/license/loader interaction), and `provider_id="ghidra"` was unavailable (`GHIDRA_INSTALL_DIR` not set). Findings below are therefore **static/observational** (binary metadata + strings/imports + cross-references to existing repo evidence in `ARCHITECTURE.md`, `RESEARCH.MD`, `OPENTV.md`) and explicitly distinguish inference from decompiled fact.

> Scope: this documents what the shipped `aurora.elf` appears to do and how it is structured, to inform safe modification of the stock image (custom UI/apps/mods). It does **not** claim complete decompiled truth where control/data flow was not recovered.

## 1. Binary identity

| Field | Value |
|---|---|
| Format | ELF 32-bit LSB executable, ARM, EABI5 (GNU/Linux) |
| ABI | UNIX - GNU, hard-float (`Flags 0x5000400, Version5 EABI, hard-float ABI`) |
| Link | Dynamically linked, interpreter `/lib/ld-linux-armhf.so.3` |
| Target OS | `for GNU/Linux 2.6.32` (build target tag) |
| Build ID | `08f88726e6a6d5edbb6b2ad54c008866feba919c` |
| Stripped | Yes (stripped) |
| Entry point | `0x006f3e5d` |
| File size | ~28 MiB (27.4M on device `/mtd_apexe/board/com.nvt.idtv/aurora.elf`, Jul 7 2020) |
| SHA-256 (extracted copy) | `c7f1c7b50a68721d25a6704cc7d792e39a6a72c15567794dda1c9cf25626084b` |
| Strings extracted | 197,142 (`strings -n 6`) |

Observed runtime identity/role (from strings + repo): main **idtv** application (`aurora.elf`), launched by appmgr/`run_aurora.sh` (`/vendor/com.nvt.idtv/aurora.elf`), participates in idtv/appmgr semaphore handshake and watchdog/liveness (see §6).

## 2. ELF structure (high level)

- **33 sections**, 9 program headers. `LOAD` segments include large RX text/rodata and RW data/bss; `GNU_STACK` RW. Large `.ARM.exidx/.ARM.extab` present (exception/unwind tables).
- **Key sections (sizes from `readelf -S`):**
  - `.text` 0xb92b8c (~11.4 MiB) — primary executable code
  - `.rodata` 0x2ed478 (~2.9 MiB) — constants/strings/tables
  - `.dynstr` 0x46339c (~4.4 MiB), `.dynsym` 0x171d30 — very large dynamic symbol/string tables (many imports/exports)
  - `.data/.bss/.dynbss` significant RW/static state
  - `.init_array` 0x1ddc, `.dynamic` present
  - `.gnu.liblist`, `.gnu.conflict`, versioning sections present (prelinked/GNU toolchain traits)
- **Interpretation:** a large, monolithic C/C++ application (stripped, hard-float ARMv7) with extensive dynamic dependencies into platform middleware.

## 3. Dynamic dependencies (NEEDED) — subsystem map

`aurora.elf` links against a very broad set of libraries, indicating it integrates most TV subsystems directly (not a thin shell). Grouped by role (observed from `DT_NEEDED`; exact usage requires decompilation):

| Subsystem | Libraries (examples) |
|---|---|
| Core/runtime | `libc`, `libm`, `librt`, `libdl`, `libpthread`, `libgcc_s`, `libstdc++`, `ld-linux-armhf` |
| Crypto/TLS | `libssl`/`libcrypto` (1.0.0), `libnss3`, `libssl3`, `libsmime3`, `libnssutil3`, `libnspr4`, `libplc4`/`libplds4`, `libmhash` |
| GLib/GObject/IO | `libglib-2.0`, `libgobject-2.0`, `libgio-2.0`, `libgmodule-2.0`, `libsoup-2.4`, `libffi`, `libnghttp2`, `libwebsockets` |
| Media/framework | `libgstreamer-1.0`, `libgstbase`, `libgstapp`, `libgstaudio`, `libgsttag`, `libgstcontroller`, `libgstnvtsink`, `libnvtmediainfo` |
| Codecs/FFmpeg | `libavcodec/format/util` (58/58/56), `libswresample`, `libavdevice`, plus older ffmpeg libs also referenced (`libav* 50/52` seen in tail), `libffmpeg`, `libliveMedia/groupsock/UsageEnvironment` |
| Audio | `libasound`, `libtinycompress`, `libportaudio`, audio DSP/player/resource libs (`libAudioPlayer`, `libAudioResources`, `libAIP` etc.) |
| Graphics/UI | **DirectFB/fusion/sawman** (`libdirectfb-1.7`, `libfusion*`, `libdirect*`, `libfusiondale`, `libsawman`), **Mali** (`libmali`), fonts/images (`libfreetype`, `libfontconfig`, `libpng16`, `libjpeg`/`libturbojpeg`, `libexpat`) |
| Novatek/platform (NDAL & HAL) | `libNDAL3`, `libNDAL_EX`, `libes2tee`, `libnteec`, `libnbinder`, `libnpc`, `libnam`, `libnvtmediainfo`, `libcrypt_ntk`, `libhdcp_ntk`, `libhdcp2_platform`, `libdrmkeyaccess`, `libttx`, `libdsub`, `libgstnvtsink`, `libp2p`, `libwfd`, `libnetview`, `libbsa`, `libmxml/jsmn`, `libsqlite3` |
| DRM/protected media | `libWasabi` (PlayReady-related in this ecosystem), `libSkb`, `libhdcp*`, `libdrmkeyaccess`, TEE libs; Marlin/TA assets handled elsewhere but app integrates DRM flows |
| Voice/Alexa (AVS SDK components) | `libAVSCommon`, `libAVSSystem`, `libDefaultClient`, `libACL`, `libADSL`, `libAFML`, `libAlerts`, `libCapabilitiesDelegate`, `libCBLAuthDelegate`, `libCertifiedSender`, `libContextManager`, `libEqualizer*`, `libESP`, `libExternalMediaPlayer`, `libKeywordDetectorProvider`/`libKWD`/`libpryon_lite`, `libMRM`, `libInteractionModel`, `libNotifications`, `libPlaybackController`, `libPlaylistParser`, `libRegistrationManager`, `libSettings`, `libSpeakerManager`, `libSpeechSynthesizer`, `libSQLiteStorage`, `libTemplateRuntime`, `libBluetooth`, `libAMAZONLITE` |
| Video4Linux/DRM | `libv4l2`, `libv4lconvert`, `libdrm` |
| Parsers/misc | `libxml2`, `libtsparser`, `libstagefright_foundation`, `libusb-1.0`, `libz` |

**Implication:** aurora is the central orchestrator binding UI, tuner/broadcast, HDMI/CEC, media playback, networking, apps (browser/Cobalt/OTT), DRM, voice, and platform services — consistent with the "idtv" monolith described in repo docs. Modifying behavior often means interacting with these platform libs/contracts, not just patching one subsystem.

## 4. Functional areas (inferred from strings)

String corpus is large (197k). Counts by broad pattern (case-insensitive keyword hits): `ui_app ~23.7k`, `av_media ~18.0k`, `input ~12.0k`, `update_config ~11.0k`, `service_factory ~10.2k`, `network ~5.0k`, `storage_fs ~4.9k`, `boot_init ~3.9k`. Below are **representative observed strings** grouped by area (illustrative, not exhaustive).

### 4.1 Process lifecycle, IPC, and liveness
- Semaphores/handshake: `mysem_idtv`, `sem_post(semaphore_idtv) fail`, `open semaphore_idtv failed...`, `mysem_appmgr`, `sem_wait(semaphore_appmgr) fail`, boot timing logs `ICE_APM ... wait appmgr ready start/done`.
- Privileged/appmgr integration: `COM.NVT.PRIVSERVER`, `COM.NVT.PRIVSERVER.CB`, `gbAppMgrReady`, `pkill -f appmgr` appears in flows.
- Suspend/resume/state: `idtvSuspend`, `idtvResume`, `Samba2idtv_Server_Init`, idtv state get/set messages.
- Watchdog/system: `[PLAT-SYS]watchdog timeout %d sec.` and numerous task/thread/semaphore strings.
- Version marker: `aurora_trunk_dtv-2020-07-07-15-02-32-dev` (embedded string).
- **Significance for custom mods:** replacing/killing aurora without satisfying appmgr/privserver/watchdog/semaphore contract can trigger resets (consistent with observed takeover reboot).

### 4.2 Filesystem paths, config, and profiles
- Writable/config: `/conf/fto.bin`, `/conf/service_menu.txt`, `/conf/hotel.tag`, `/conf/fti.tag`, `/conf/qstdby.tag`, `/conf/dolby.bin`, `/conf/mac.txt`, `/conf/PCF.pcf`, `/conf/sqlite_db/settingsDB.db`, `/conf/recover_count.txt`, `/conf/reset_count.txt`, `/conf/wdttaskon`, `/conf/force_enable_coredump`, `/conf/standalone_browser.bin`, `/conf/browser/*`, `/conf/rwdb.txt`, etc.
- Buffer/runtime: `/buffer/logo.jpg`, `/buffer/bootlogofilename`, `/buffer/browser_home/*`, `/buffer/conf_backup/*`, `/buffer/com.nvt.cobalt`, `/buffer/com.nvt.nflx`, `/tmp/stdout.idtv`.
- Vendor/system: `/vendor/browser_home/*`, `/vendor/com.nvt.nflx/*`, `/mtd_apexe/board/...`, `/mtd_rwarea/com.nvt.amazon/*`.
- Profile/config concepts: `hwprofile`, `swprofile`, `devprofile`, print/profile diffs (`diff -q ... hwprofile.bin`, `swprofile.bin`), `set_html_plugin_profile_status`, power/profile modes, PQ/EDID profile handling.
- **Note:** strings reference `DownloadProfile.mb230` and USB/profile/EDID/HDCP/ROFIX-related operations; aligns with service-menu `PerformUSBOperations` behavior documented in `RESEARCH.MD` (static evidence of support; exact control flow not decompiled here).

### 4.3 USB / service operations / credentials / ROFIX (inferred)
- USB/profile/config handling strings: `DownloadProfile.mb230`, `screen_capture_usb` ("Capture specified surface as bmp to USB stick..."), USB enable controls.
- Credential/key flows (named): `PRODUCTION_CREDENTIALS.BIN`, `mb230_hdcp.bin`, `mb230_hdcp2.bin`, HDCP/HDCP2/CI+/DTCP load/test/diagnostic APIs, pairing-protocol loaders, `ROFIX`/`ROFIXBAK` checks and erase messages, EDID read/verify/swap/print paths (1.4/2.0/VSVDB/HDR/Dolby Vision recovery strings).
- **Caution:** these are sensitive security/DRM/identity-related areas; modification can break playback/compliance or device identity. Treat as high-risk; do not exfiltrate/publish secrets.

### 4.4 Updates / OAD / OTA
- `oadWriteFlashAndReboot`
- `echo nvt_trigger_update > /tmp/trigger_reboot`
- `ICE_CallistoStartUpgradeSoftwareFromUSB`
- Software update controllers/timers/messages (extensive `Novo/Nebula...SoftwareUpdate...`, `startUpgradeSoftwareFromUsb`, `startUpdateSearchTimer`, etc.)
- `/conf/fto.bin` and update-state related flows (consistent with ARCHITECTURE.md notes on FTO/update counters/state).

### 4.5 Input, IR, CEC, HDMI
- IR: `ice_Netflix_IR_Callback`, IR simulator/enable/disable messages, IR-to-key handling strings; DirectFB UART IR stack used at runtime (per repo) with keymaps in `/vendor`.
- UART/serial: `/dev/ttyS0`, uart options/settings.
- CEC: `CECEnableOnOff`, `CECAutoPwrOnOff`, `ICE_LowPowerSetCECEnable`, `ICE_LowPowerSetCECOneTouchPlay`, HDMI ARC/port strings.
- HDMI: extensive HDMI timing/mode/EDID/Dolby/HDR/HLG handling, enhanced colors, true black, per-source PQ behavior.
- Remote/app keys (examples): `KeyNetflix`, `KeyAmazon`, `KeyMediaBrowser`, etc. (also present in keymaps).

### 4.6 Apps, browser, OTT, casting, media
- Browser: `initializeBrowser`, `CheckBrowserFontFile`, `browser_type`, browser home/font/speed-dial paths, standalone browser flag (`/conf/standalone_browser.bin`).
- OTT/integrations: Netflix (dial settings, IR callbacks, PQ/timing paths), Amazon/Prime/Alexa (AVS libs linked, Amazon env/data paths), Cobalt/YouTube paths referenced in buffer/vendor areas.
- Casting/network media: DLNA (`ICE_MediaPlayerSetDLNATotalPlaybackTime`, DLNA details), Miracast/WFD (`libwfd`), P2P/DIAL-related components.
- Media pipeline: GStreamer + NVidia/Novatek sink + FFmpeg/liveMedia/tsparser, teletext/subtitles (ttx/dsub libs), DVB/CI-related platform integrations implied.

### 4.7 Factory/service/hotel/diagnostics
- Service/factory/hotel: `/conf/service_menu.txt`, factory reset strings, `hotel.tag`, hotel startup/source/volume/position settings, power-up modes (FTI/hotel/profile).
- Diagnostics: diagnostic enable/test APIs (HDCP/EDID/telnet/USB logging etc. referenced by name), UART debug toggles, coredump forcing (`/conf/force_enable_coredump`).

### 4.8 Networking
- DHCP/network scripts/tools: `udhcpc` invocations/scripts (`/etc/udhcpc/default.script`, pid/info in `/var/run` or `%s` paths), `zcip` fallback, `script_network.sh`, interface bring-up patterns (consistent with ARCHITECTURE.md: eth0 MAC/DHCP behavior, `script_network.sh` linkage).
- Telemetry/remote-like features exist as named diagnostics/settings (e.g. telnet enable/disable APIs appear in strings), but enablement/runtime behavior requires decompilation or live observation.

## 5. Observed runtime model (correlated with repo evidence)

- **Launch chain (MD30010/stock layout):** init/rc runs startup scripts → `/vendor/run.sh`/appmgr/debug ini select idtv path; `run_aurora.sh` can run `aurora.elf` directly or via debug/CIFS/gdbserver paths depending on `/conf` flags (e.g. `remote.txt`) — see `ARCHITECTURE.md` §"Boot & init chain" / "Code-execution surface".
- **Environment sensitivity:** aurora expects full stock environment (BROWSER_DIR/WORKING_PATH, GStreamer/DirectFB/platform vars). Missing env can cause fatal startup issues (documented in jailbreak saga, `README.md`).
- **Liveness:** must satisfy idtv semaphore/handshake with appmgr/privserver and watchdog expectations; naive kill/replace without preserving contract can reboot the TV.
- **Input:** IR over UART/GPIO via DirectFB userspace driver; no evdev remote.
- **Display:** DirectFB/fusion/sawman + Mali/GPU + NVTV platform sinks; compositing owned by running stack.

## 6. Modification surface (for "full custom / new app entries / custom mods")

This is a **static assessment** to guide safe work; validate each change on hardware with backups and recovery paths.

### 6.1 Lower-risk, practical levers (configuration & writable volumes)
- **`/conf` (apdat0, rw UBIFS):** rich control/config surface (profiles PQ/PCF/ptf/AQ refs, service/hotel flags, browser/standalone flags, coredump/debug toggles, app env/data hooks). Service-menu USB operations already manage specific files; U-Boot volume-write channel can replace whole volume (see `stage1/uboot`, `ARCHITECTURE.md`, `OPENTV.md`) — **first real writes should be backed up and reversible**.
- **`/buffer` (rw):** runtime/cache area (browser/cobalt caches, backups); useful for transient experiments.
- **Telnet/root context (if present):** enables rapid iteration (upload/run custom binaries like `hello-world`, `gui-hello-world`) without flashing.

### 6.2 App-entry / launch customization points (evidence-backed candidates)
- **Script/ini-driven selection:** `run.sh`/`run_aurora.sh`, appmgr `nvt.app.debug.ini` flows, and `/conf` hooks (`remote.txt`, `run_with_dwelf` + `/buffer/aurora.elf` where applicable, `remote_nfs.txt`) are documented extension/debug paths. Feasibility on a given firmware must be confirmed against installed files.
- **Coexistence/liveness constraint:** any replacement GUI/app that takes over idtv role must preserve or safely emulate required handshakes/watchdog behavior, or run as a managed sidecar.

### 6.3 Deep modification (higher effort/risk)
- **Patching `aurora.elf` itself:** stripped, 28MB, hard-float ARM, heavy platform-lib coupling and C++ structures — feasible only with solid RE (disassembly/decomp, ABI/lib contracts) and careful binary patching; risk of instability, DRM/key breakage, or boot/liveness regressions.
- **`ap0/ap1` (SquashFS-in-UBI) changes:** can alter shipped apps/resources/scripts/modules; requires image rebuild + UBI write and full verification (signatures/boot chain constraints apply to signed partitions; userspace volumes writable via known channels but must preserve layout/CRC expectations).
- **New app entries in stock UI:** likely require understanding aurora/appmgr/portal configuration, resource manifests, and possibly binary or packaged-app formats — not fully recoverable from strings alone; decompilation of relevant UI/app-manager paths needed.

### 6.4 Hard constraints (do not violate)
- **Secure boot / signed chain:** do not flash unsigned boot components (XBOOT/DDRCFG/SECOS/U-Boot/FDT/kernel as applicable). `nvt_sign` and platform security expectations remain.
- **DRM/keys/credentials/ROFIX/HDCP/MAC:** high sensitivity; avoid modification/exfiltration.
- **Reversibility:** keep full NAND/SPI backups (done for MTDs except unreadable `mtd5 misc` in this session; SPI NOR backup still pending). Prefer `/conf`-scoped, reversible experiments first.

## 7. Gaps and recommended next RE steps

- **Decompilation/callgraph/data-flow:** retry REA with a working provider (Hopper GUI readiness/license resolved, or configure `GHIDRA_INSTALL_DIR` for Ghidra 12.1.x, or IDA MCP) to obtain function-level pseudocode, xrefs, and structures — essential for "decode fully" and safe patching.
- **Targeted areas to reverse:** (a) main/init and appmgr/privserver handshake, (b) input dispatch (IR key → action) and menu/launcher flow for "new app entries", (c) USB `PerformUSBOperations`/profile handling, (d) update/OAD state machine (`fto`, `nvt_trigger_update`, `oadWriteFlashAndReboot`), (e) service menu/factory gates, (f) browser/Cobalt/portal integration points.
- **Correlate with filesystem:** inspect `/vendor/com.nvt.idtv/` (scripts, configs, resources), `/vendor/data/nvt.app*.ini`, and `/conf` runtime state on-device to map strings to actual behavior.
- **Dynamic observation (authorized/controlled):** tracing/logging, `strace`-like instrumentation where available, or gdbserver/CIFS debug hooks (documented) can validate hypotheses that static analysis cannot.
- **Evidence hygiene:** when decompilation becomes available, attach Evidence IDs/procedure addresses to each claim and separate observed vs inferred behavior.

## 8. Artifacts produced

- Extracted binary: `/tmp/opencode/rea-targets/aurora_stock.elf` (from `mb230-full-backup/mtd12_fs0.bin`)
- Strings corpus: `/tmp/opencode/rea-targets/aurora_strings.txt` (197,142 lines)
- This report: `AURORA_ELF_ANALYSIS.md`
- REA session: opened/closed (no provider analysis results captured due to provider unavailability)

## 9. Summary

`aurora.elf` is the **large, monolithic, stripped ARMv7 hard-float idtv application** at the center of the MB230 stack, dynamically bound to Novatek platform HALs (NDAL/DirectFB/Mali/GStreamer), DRM/HDCP/TEE components, networking, browser/OTT integrations, and AVS/Alexa libraries. Static evidence (ELF + extensive strings) maps clear responsibilities: lifecycle/liveness IPC with appmgr/privserver, rich `/conf`-driven configuration (profiles/PQ/EDID/service/hotel/FTI), USB/service/profile/credential handling surfaces, OAD/software-update paths, IR/CEC/HDMI/input and media pipelines, and multi-app/portal/browser integrations. For "full custom" goals, the safest near-term path is leveraging **writable config/hooks and sidecar/custom apps under controlled liveness**, while full binary modification or native "new app entry" integration will require decompilation-grade RE (Hopper/Ghidra/IDA) of targeted subsystems plus careful, reversible on-device validation.