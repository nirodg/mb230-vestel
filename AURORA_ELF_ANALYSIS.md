# aurora.elf (stock MB230 idtv app) — analysis

**Target:** `com.nvt.idtv/aurora.elf` (stock main TV application on Vestel/Novatek MB230 "Kylo")
**Analyzed binary:** extracted from `mb230-full-backup/mtd12_fs0.bin` → UBI volume `ap0` (SquashFS) → `com.nvt.idtv/aurora.elf`
**Local copy:** `/tmp/opencode/rea-targets/aurora_stock.elf` (working extraction for this session)
**Analysis date:** 2026-11-15

**Methods:**
- **Static:** `file`, `readelf` (headers/sections/segments/dynamic/NEEDED), and `strings -n 6` (197,142 strings) + targeted searches, cross-referenced with `ARCHITECTURE.md`, `RESEARCH.MD`, `OPENTV.md`.
- **Ghidra headless decode (completed):** Ghidra **12.1.4 PUBLIC** (`analyzeHeadless`, ARM:LE:32:v8) auto-analysis of the extracted ELF (~90,606 functions recovered) with scripted export of function inventory, key strings/xrefs, and targeted decompilation for mod-relevant subsystems. See **[`aurora-re/GHIDRA_DECODE.md`](aurora-re/GHIDRA_DECODE.md)** for function-level evidence (addresses, callers/callees, decompiled logic) covering lifecycle/suspend-resume/liveness, input/key dispatch, USB service operations (`PerformUSBOperations`), Callisto/NDFW OAD update flow, profiles/service/PQ, and modding implications. REA MCP provider decomp was not available to the live session; decode was performed via Ghidra headless directly.

> Scope: documents what the shipped `aurora.elf` does and how it is structured to inform safe modification of the stock image (custom UI/apps/mods, new app entries). Decompiled C is Ghidra’s reconstruction of stripped code (approximate types/names) but grounded in analyzed control/data flow and call/string evidence. No confidential material included.

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
- **Telnet/root context (if present):** enables rapid iteration (upload/run custom binaries like `usb-injection/tools/hello-world`, `usb-injection/tools/gui-hello-world`) without flashing.

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

## 7. Ghidra decode status and remaining work

**Completed (see [`aurora-re/GHIDRA_DECODE.md`](aurora-re/GHIDRA_DECODE.md)):** headless Ghidra auto-analysis and targeted decompilation for key mod-relevant paths with addresses/call graphs — `idtvSuspend/Resume` (STR/liveness coupling), `ice_KeyEventDispatchThread` (UART key read, long-press/repeat/APM context, dispatch and USB-op trigger path), `PerformUSBOperations` and helpers (`NonVolatile_CopyUSB`, `DEV_MTD_UpdateImage`, ROFIX/tcon/PQ/conf flows), Callisto/NDFW update chain (`ICE_CallistoWriteBytesToFlash`, `upgradeSoftwareFromUSB`, `CallistoActivateNewCode` → `nvt_trigger_update` reboot trigger, USB-upgrade start wrappers), service/PQ/profile reporting (`ICE_ServiceGetPQandAQFileNames`), and subsystem mapping.

**Still valuable for deeper “new app entry” / full custom UI mods:**
- **Input→action/menu/launcher mapping:** fully resolve `ice_KeyEventDispatchThread` dispatch tables/handlers and focus/APM transitions to concrete UI/app actions.
- **App-manager/UI framework (Nebula/EASI/Novo/CA*):** decompile registration/launch/menu-entry points to identify where stock app entries are defined and how to add/swap them.
- **`PerformUSBOperations` rodata:** resolve all string/table indirections to a precise USB file manifest and per-file handling.
- **Init/main and IPC handshake:** trace binary entry/startup to appmgr/privserver/semaphore/watchdog contract details.
- **On-device correlation:** map findings to `/vendor/com.nvt.idtv/`, `nvt.app*.ini`, and `/conf` runtime state; validate hypotheses via controlled, reversible experiments (telnet/sidecars, `/conf` hooks) with backups.

## 8. Artifacts produced

- Extracted binary: `/tmp/opencode/rea-targets/aurora_stock.elf` (from `mb230-full-backup/mtd12_fs0.bin`)
- Strings corpus: `/tmp/opencode/rea-targets/aurora_strings.txt` (197,142 lines)
- Static report: `AURORA_ELF_ANALYSIS.md`
- **Ghidra decode report:** `aurora-re/GHIDRA_DECODE.md` (function-level evidence; Ghidra 12.1.4 headless, project/exports generated locally under `/tmp/opencode/ghidra-proj/` and `/tmp/opencode/ghidra-out/`, not committed)
- REA session: used for earlier attempts; live REA MCP in that session lacked a ready Ghidra/Hopper provider, so decode was completed via direct headless Ghidra.

## 9. Summary

`aurora.elf` is the **large, monolithic, stripped ARMv7 hard-float idtv application** at the center of the MB230 stack, dynamically bound to Novatek platform HALs (NDAL/DirectFB/Mali/GStreamer), DRM/HDCP/TEE components, networking, browser/OTT integrations, and AVS/Alexa libraries. Static evidence (ELF + strings) combined with **Ghidra headless decompilation** (`aurora-re/GHIDRA_DECODE.md`) now documents key control flows with function-level evidence: suspend/resume/liveness coupling, centralized UART key dispatch (and privileged triggers such as USB operations), detailed USB service operations (`PerformUSBOperations` and helpers touching profiles/PQ/configs/logs/MTD/ROFIX/tcon), and the Callisto/NDFW USB-upgrade/OAD activation path (including `nvt_trigger_update` reboot). For "full custom" goals, the safest near-term path remains **writable config/hooks and sidecar/custom apps under controlled liveness** with reversible backups; native “new app entry” integration and deeper UI/framework mods should build on the identified Nebula/EASI/APM/dispatch targets for further focused RE and careful on-device validation.