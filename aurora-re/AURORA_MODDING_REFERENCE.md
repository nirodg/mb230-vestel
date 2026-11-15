# aurora.elf modding reference (MB230 / Kylo / idtv)

**Purpose:** comprehensive, evidence-backed reference for understanding and modifying the stock `aurora.elf` (Vestel/Novatek 17MB230, NT72671/73 “Kylo”, Horizon 50HL7530U/B lineage) to enable custom apps, UI behavior changes, and reversible stock-image mods.

**Source of truth:** Ghidra 12.1.4 headless decompilation/analysis of extracted stock `aurora.elf` (`ap0` SquashFS from `mtd12_fs0.bin`) plus prior static findings in this repo. Decompiled C is Ghidra’s reconstruction of stripped C/C++ (names/types/locals approximate); **addresses, call targets, string refs, constants, and control/data flow cited here come from analysis artifacts** generated locally (`/tmp/opencode/ghidra-proj/aurora121`, `/tmp/opencode/ghidra-out/*.c|*.tsv|*.txt`). No REA Evidence IDs (provider unavailable in-session).

**Non-goals / constraints:** do not modify or exfiltrate signed boot chain, DRM/HDCP/ROFIX/credentials/keys, or device identity (MAC/serial). Prefer reversible `/conf`/sidecar experiments with full backups. No confidential material is included.

> Cross-references: `AURORA_ELF_ANALYSIS.md` (overview/status), `aurora-re/GHIDRA_DECODE.md` (function-level decode log), `ARCHITECTURE.md` (boot/partitions/SoC), `RESEARCH.MD` (service-menu USB ops, profiles/PTF/EFSL), `SESSION_2026-11-15_ROOT_BACKUP.md`, `hello-world/`, `gui-hello-world/`.

---

## 1. Binary and runtime identity

| Field | Value |
|---|---|
| Binary | `com.nvt.idtv/aurora.elf` on device `/mtd_apexe/board/com.nvt.idtv/aurora.elf` (from `ap0`) |
| Format | ELF32 ARM LE, EABI5 hard-float, dynamically linked, interpreter `/lib/ld-linux-armhf.so.3` |
| Build | stripped, BuildID `08f88726e6a6d5edbb6b2ad54c008866feba919c`, ~28 MiB, entry `0x006f3e5d` |
| Version marker | `aurora_trunk_dtv-2020-07-07-15-02-32-dev` |
| Role | Monolithic **idtv** app: UI/framework (Nebula/EASI/Novo/Cabot C++), APM/app lifecycle, input, A/V/broadcast, HDMI/CEC, networking, browser/portal/OTT (Netflix/Amazon/YouTube/Cobalt/HbbTV/MHEG), DRM/TEE/HDCP, updates (Callisto/NDFW), profiles/PQ/service/factory, USB service ops. |
| Key deps (DT_NEEDED) | DirectFB/fusion/sawman, Mali, GStreamer/FFmpeg/liveMedia, ALSA, GLib/GObject/soup, OpenSSL/NSS, SQLite, Novatek NDAL/TEE/HDCP/NDFW/libs, AVS/Alexa components, Wasabi/DRM libs, etc. |

**Runtime expectations:** stock environment/paths (`/vendor`, `/conf`, `/buffer`, `/tmp`, BROWSER_DIR/WORKING_PATH, GStreamer/DirectFB vars), appmgr/privserver availability, semaphore/IPC handshake, watchdog/liveness, UART/IR and display pipelines owned by platform stack.

---

## 2. Startup and process model

### 2.1 Entry and bootstrap
- **`_start` (`006f3e5c`)** → `__libc_start_main(entry, stack, init, fini, rtld_fini, stack_end)` then `abort`. Actual application entry is resolved via init/startup linkage (multiple `main`-named symbols exist in image; behavior correlates to runtime).
- **`main` (`0069d950`)**: if invoked with args, handles `-v/--version` and `-h/--help` by printing SVN URL/revision (`getSVNURL`, `getSVNGlobalRevisionInfo`) or usage; otherwise (normal start) calls **`FUN_00728608`**.
- **`FUN_00728608` (primary bootstrap, caller `0069d950`)** sequence:
  1. `ICE_InitialiseSystemMemory()` (debug/log init, signal handlers registration `debugRegisterSignalHandlers`).
  2. `getpid()` stored to global.
  3. `ICE_DebugInit()` (waits for console/debug readiness, registers debug commands; e.g. accesses control path and sleeps until ready).
  4. `profileManagerStart()` (creates `ProfileManager` singleton, attaches ROM profiles: `ROMProfile` instances for multiple profile sources via `ProfileManager::attachProfile`).
  5. `FROST_DebugStartConsole()` (registers console commands/tasks, creates debug console/testtool socket tasks if enabled by profile/OS init state).
  6. `ICE_HardwareInit()` (large platform bring-up; see below).
  7. `ICE_InitRTC()` (`PLAT_OS_SyncRTCFromSTBC`).
  8. `eclipseStart()` → `preemptiveNetworkInit()`; `new StandardSettop()`; `StandardSettop::initialise()`.
  9. Infinite `FROST_Sleep(...)` loop (app runs via initialized subsystems/tasks/framework threads).

> Another `main` symbol (`006a0ac4`, `CECInterface::main`) exists in C++ context; not the idtv process bootstrap above.

### 2.2 Hardware/init (`ICE_HardwareInit`, `0073bac0`)
Very large bring-up: profile/board/feature flags, production/non-smart checks, kernel log/coredump/debug gating (`/conf/force_enable_coredump` handling paths), fast-boot/STR/special-key/exit-type and power-up parameter restore, MCU/RC/EDID order, panel/tcon/VOUT/DSP/NIM/audio/PQ/Callisto/DRM/CEC/network/USB/storage init, environment setup, tag/file confirmations, debug menu/command registration hooks, sync to xboot/MCU as needed. Central dependency for stable operation.

### 2.3 Appmgr/privserver/liveness coupling
- **APM readiness:** `ICE_APM: [BOOT] ICE_APM wait appmgr ready start/done` strings; APM init waits on appmgr.
- **Process control over appmgr IPC:** `LIBNAM_APP_SendCommand` used by
  - `ice_APM_Register` (`00784254`) → `LIBNAM_APP_Register(...)`
  - `ice_APM_StartProcess` (`00784604`, cmd `0x106`, payload includes name/args, type=2)
  - `ice_APM_StopProcess` (`007846a0`, cmd `0x106`, type=1, stop flag)
  - `ice_APM_ProbeProcessStatus` (`00784740`, cmd `0x104`, returns status)
- **Semaphores/identifiers (strings):** `mysem_idtv`/`semaphore_idtv`, `mysem_appmgr`/`semaphore_appmgr`, `COM.NVT.PRIVSERVER(.CB)`.
- **Observed behavior:** killing/replacing aurora without satisfying handshake/watchdog/appmgr expectations can reboot (see `gui-hello-world` takeover notes). `pkill -f appmgr` appears in flows.

### 2.4 Suspend/resume (STR)
- **`idtvSuspend` (`0073a3a4`)** / **`idtvResume` (`0073a708`)** (from `ice_hardware_SuspendToRam` paths): deep coordination with APM, MCU WoL/WoW, CEC, Wi-Fi/BT, tuner/NIM/VBI, panel/OSD/backlight/bootlogo, PQ backup/restore, UART IR sim tasks, HDCP/AMP, device suspend, state sync.
- **Implication:** aurora is the STR owner; replacements must preserve or avoid breaking these contracts.

---

## 3. APM (Application/Process Manager) API and model

**Init:** `ICE_APMInit` (`007842a8`, caller `APMInit`) — waits appmgr ready, sets up APM state/callbacks, prepares brand/software/version context (writable files via `PLAT_PRIVCTRL_System`/fopen/fwrite), `ice_APM_Register`, creates tasks (`PLAT_OS_CreateTask`), registers NPC/PQ APM callback.

**Core run/transition:** `ICE_APMRun` (`00785280`) — mode/app-id driven foreground management: OSD/plane/alpha and A/V path switching, `ice_APM_Probe/Start/StopProcess`, DIAL/URL handling, PQ/picture restore, input/focus coordination.
- **Resolved managed process names (rodata):** `netflix` (`01254ad3`), `amazon` (`01262017`), `youtube` (`01476f48`), `youtube_test` (`01260d32`).
- **Resolved launch/URL fragments:** Netflix dial/additional-data (`.../apps/Netflix/dial_data`, `source_type=19`), YouTube (`.../apps/YouTube/dial_data`, `launch=menu|remote`), `dialLaunch`, recommendation params `youtube_recommendation_video_id|channel_id|playlist_id`.

**Other APM surfaces (symbols/decomp):** `ICE_APMStop/Suspend/Wakeup`, focus/resource get/lose, `ICE_APMHandleKeypress` (`00784094`), hotkey checks, Netflix standby/status/logo helpers, logout helpers (Amazon/YouTube/Netflix), language/country/sleep mode, running-app queries.

**Modding note:** first-class “new app” behavior in stock stack requires integration across launcher/UI registration, APM run/start/stop, focus/resource, and input/hotkeys — not just dropping a binary.

---

## 4. Input system (UART/IR) and key dispatch

### 4.1 Pipeline overview
- **`ice_KeyEventDispatchThread` (`00763dc0`)**: main key loop (no named callers recovered; typical thread entry). Reads via **`DEV_Uart_GetKey`** (`00840608`), times with `PLAT_OS_GetTimeMS/TimePlus/TimeAfter`, decodes/maps via **`FUN_00761880`** (`00761880`), applies long-press/repeat logic via **`ice_IsButtonLong`** (`00762aa0`), consults repeat/hotkey/APM/focus/profile state (`ICE_IsKeyRepeatOn`, `ice_DFB_IsHotKey`, `ICE_APMGetRunningApp`, `ICE_APMGetSleepMode`, `Profile_IsFairFeaturesEnabled`, `Profile_IsAlexaEmbeddedEnabled`, etc.), and dispatches via **`FUN_00761cf8`** and related handlers/callback hooks.
- **`FUN_00761880`**: protocol/type-aware decode of raw key data (handles multiple RC encodings/types e.g. 0/1/4/6/7 paths, address/system-code validation against stored values) and maps command byte through **`mapVestelKey`** (`007617c0`); returns **`0x2f1`** as invalid/no-key.
- **`mapVestelKey`** (`007617c0`): table lookup over Vestel key map (scan up to table bound; match byte → mapped key id, else `0x2f1`). Optional debug print when remote-control debug profile flag enabled.
- **`ice_IsButtonLong`** (`00762aa0`): tracks press/release/repeat timing and triggers long-press dispatch (`ice_dispatch_long_button`, `007629b4`) / repeat callbacks; cooperates with dispatcher state.
- **`FUN_00761cf8`** (key action/route): enforces conditions (e.g. suspend-to-RAM on `0x21f` in specific state, DVD-source key filtering `IsTheKeyEnabledInDvdSrc`, hotel-mode behavior, fair-features gate, Netflix/hotel/app-running routing) and forwards to Netflix callback path or **`ice_SendKeyToMw`** for middleware/UI; special handling for `0x21f`/`0x9ef` with `ice_CheckDiagnosticSelectPatternState`.
- **Helpers:** `ICE_KeyRepeatOn/Off`, `ICE_CallKeyPressFunction` (`007649c8`), `ice_SendKey` (`00765384`), `ice_Netflix_IR_Callback` (`0076330c`), `ICE_RemoteInit`/UART IR simulator hooks.

### 4.2 Hidden USB-operations trigger (decompiled evidence)
In `ice_KeyEventDispatchThread` (`00763dc0`):
- For keys in **`0x200–0x209`** (digit-key range in internal keyspace), it accumulates a numeric sequence via `FUN_0122e3dc(acc * 10 + (key - 0x200), DAT_007643c4)` (accumulator stored at `*DAT_007643c0`).
- If accumulated value equals **`DAT_007643c8 = 472569`** (resolved rodata), it calls **`PerformUSBOperations()`** and resets accumulator.
- Keys in **`0x9d0–0x9d9`** do not force a reset in that branch; other non-matching key paths reset the accumulator (`*DAT_007643c0 = 0`). `DAT_007643c4 = 1000000` is passed as a parameter to the accumulator helper.

**Interpretation (grounded in constants/logic):** the dispatcher implements a hidden digit sequence whose accumulated value is **472569** (digits `4,7,2,5,6,9`) that triggers USB service operations, subject to the same `DEV_Uart_GetKey`/key-mapping path and runtime state. This is distinct from the user-facing service-menu access code documented in `RESEARCH.MD` (e.g. `MENU 4725`) — do not conflate without on-device confirmation.

### 4.3 Practical input mod points
- Understand/override at `mapVestelKey`/decode stage for raw→key remap, or at `FUN_00761cf8`/middleware delivery for action routing.
- `ICE_CallKeyPressFunction` provides a programmatic injection path into dispatch logic (used by UI/remote-command helpers).
- Long-press thresholds and special keys are profile/feature gated in several paths.

---

## 5. USB service operations (`PerformUSBOperations`) — manifest and behavior

**Implementation:** `PerformUSBOperations` (`0076c488`), callers include Nebula wrapper `performUSBOperations` and `ice_KeyEventDispatchThread` (hidden sequence). Uses `RmDev_GetLastMountPoint`, `FUN_00766354` (marker `access`), `FUN_00766e30` (conditional copy/sync), `NonVolatile_CopyUSB`, `DEV_MTD_UpdateImage`/backup, ROFIX/tcon/panel-param helpers, `system`/`ice_system_command`, `sync`, `PerformConfBackup`.

**Behavior summary:** mount removable media; marker-gated import/export of profiles/configs; collect/package logs/state to USB (timestamped, mutex-protected aggregation/tar); boot-logo validate/write to MTD and STR sync; copy PQ/PCF/PQF/PTF/EDID/AQ/Dolby/sound/browser/network/misc files both directions per markers; ROFIX update/backup from USB dirs; TCON update/backup; panel params sync to xboot data; final sync/conf backup.

**Resolved rodata markers/paths (evidence-backed, non-exhaustive):**
- **Markers/triggers:** `/UploadNvram.mb230`, `/DownloadNvram.mb230`, `/DownloadBI.mb230`, `/DownloadProfile.mb230`, `/DownloadPQ.mb230`, `/DownloadSpi.mb230`, `/DownloadTcon.mb230`, `/DownloadSerialModelNo.txt`, `/config_update/config_update.txt`, `/enable_coredump`.
- **Boot logo/SPI:** `/spi/boot_logo.bin`, `/logo.jpg`, `/spi`.
- **Sound/AQ/DSP ↔ `/conf`:** `/sound/AQ.bin`, `/sound/DAP_SE_SetParam.txt`, `/sound/DAPV2_SE_SetParam.txt`, `/sound/DTS_VX_AQ.bin`, `/sound/subw_config_file.txt`, `/sound/ad82586c_config_file.txt` ↔ corresponding `/conf/*`.
- **PQ/panel/Dolby ↔ `/conf`:** `/pq/PCF.pcf`, `/pq/PQF.bin`, `/pq/ptf.ptf`, `/pq/dolby.bin`, `/pq/Dolby.cfg` ↔ `/conf/PCF.pcf`, `/conf/PQF.bin`, `/conf/ptf.ptf`, `/conf/dolby.bin`, `/conf/Dolby.cfg`.
- **Browser/app config (USB-side names observed):** `/browser_parameters.txt`, `/starturl.txt`, `/default_application.txt`, `/dragonfly_server.txt`, `/iplayer_client.inf`, `/vestel_key.p12`, `/thorium_config.xml`.
- **Network/misc:** `/ntpserver.txt`, `/forced_ntpserver.txt`, `/demo_commands.txt`, `/conf/power_up.txt`; coredump flag `/conf/force_enable_coredump`.
- **Exports:** `/syslog`/log bundles to USB (timestamped).

**Helpers:**
- `NonVolatile_CopyUSB(mount,name,direction)` (`00755988`): mutexed, command-based copy of hw/sw/dev/lang/profile artifacts.
- `DEV_MTD_UpdateImage(mtd, src, offsetBlocks)` (`00835ef8`): validates/erases/nandwrite (+verify paths) — **high risk**.
- `RmDev_GetLastMountPoint` (`00768c80`): current removable mount under mutex.
- `PerformConfBackup` (`0073afac`): backs up conf state.

**Risk:** touches MTD, ROFIX, TCON, panel params, credentials-adjacent and profile data. Use only for understood, reversible operations with backups.

---

## 6. UI/application framework, launcher, and registration

### 6.1 CA application registry (in-process)
- **`CAApplicationManager::registerApp(CAStackType, ushort id, CAApplicationInfo*)`** (`00ab8874`, caller `CAStackServer::informApplicationAdd`): stores records in internal table (`this+0x100` count, **stride `0x10`**, guard **max 0x10 entries** in checked path) with type, 16-bit field, and copied `UString` app info.
- **`deregisterApp`** (`00ab88e8`) removes entries.
- **Availability/start notifications:** `informApplicationAvailable` (CI/MHEG context, subtitle/profile, async message to EASI control), `informApplicationStart` thunks/paths to HbbTV/MHEG (`ApplicationMMISession::informApplicationStart` → `INCA_MHEGApplicationStart` / `INCA_HbbTVApplicationStart`).

### 6.2 Launcher flow (Novo/DemoApp)
- **UI selection → open:** `FullScreenMarketDialog::openSelectedApp`, `FullScreenPortalDialog::openSelectedApp` resolve selected `NovoLauncherItem` (id/url/name), set logging/CID source/input name, call **`DemoApp::startLauncherApplication(id, flag)`** (`00cc7074`); on success record selected id and close dialog.
- **`DemoApp::startLauncherApplication(UString const&, bool)`** dispatches by app identifier:
  - `netflix.swf` (and availability/connectivity checks) → `handleNetflixRequest` (“Open Netflix Application”).
  - `amazon.swf` → `handleAmazonRequest` (“Open Amazon Prime Application”).
  - `youtube.swf` / `youtube_recommendation` with Cobalt/profile gating → `handleYoutubeRequest` (“Open Youtube Application from Launcher/Recommendation”).
  - Fallback: on-demand content / browser / ODC context (`launchOnDemandContentWithContext`) or UI/framework message posting.
- **Launcher data/model:** `NovoLauncherItem`, `NovoLauncherManager`, `NovoLauncherDataProvider`, `SqliteLauncherDatabaseAdapter` (insert/update/remove/sync), portal/market application list updates, recommendation shortcuts, settings/visibility updates, “My Apps”/home insert flows. `initialiseLauncherSourceItems` stubs/flows exist in dialogs/framework (some implementations minimal in decomp; population is multi-source).
- **Config/resource hints (strings):** SQLite DBs under `/conf/sqlite_db/settingsDB.db` (and backups/copies in buffer paths observed in strings), launcher SVG/menu assets and Novo* classes.

### 6.3 “New app entry” feasibility (evidence-based)
- **Potential integration layers:** (1) launcher source data feeding recognized ids/URLs/items (portal DB/config/resource pipelines), (2) `startLauncherApplication` id matching and handler/start path, (3) `CAApplicationManager`/stack notifications, (4) APM process/URL launch and focus/resource handling.
- **Reality check:** stock OTT apps are deeply integrated (dedicated handlers, process names, dial URLs, DRM/browser runtimes). Adding a *first-class* entry may require binary/framework changes or supported data-driven extension points present in this firmware build.
- **Practical mod paths:** sidecar apps via telnet/scripts; browser/start URL/config hooks; `/conf` and supported USB-imported resources; reversible UI experiments only when liveness is preserved.

---

## 7. Service menu and privileged UI paths

- **Entry/flow:** `DemoApp::onShowServiceMenu` → `DemoApp::doMenuService` (`00cb7cc4`) constructs `ServiceMenuDialog` (derived from `MyMenuDialog`/`GeneralDialog` SVG UI stack), handles modal results, module-state transitions, and can trigger USB operations via `NovoSystemConfiguration::performUSBOperations` (with DVR/removable-device checks and optional prompts/auto actions).
- **Guards/helpers:** `isServiceMenuProfilePasscodeAvailable`, `controlServiceMenuPwd`, Philips service-menu variant checks/timers, capture-password flows, `getServiceMenuInfo` (large info/report builder).
- **Files/strings:** `/conf/service_menu.txt` and service-menu related UI/dialog classes.

> User-facing access (e.g. `MENU 4725`) is documented in `RESEARCH.MD`; correlate with on-device behavior. Do not confuse with the hidden digit-sequence USB trigger in key dispatch (§4.2).

---

## 8. Software update / OAD (Callisto + NDFW)

- **USB upgrade detection/start:** `ICE_CallistoCheckUsbToUpgrade` (finds mount/package), `ICE_CallistoStartUpgradeSoftwareFromUSB` (worker thread), `upgradeSoftwareFromUSB` streams image chunks to `ICE_CallistoWriteBytesToFlash`.
- **Flash/write:** `ICE_CallistoWriteBytesToFlash` stages temp data, parses NDFW header, validates space/images, iterates and applies images via `NDFW_*` APIs.
- **Activation:** `CallistoActivateNewCode` checks `NDFW_GetUpdateStatus`, sets secure update mode, writes trigger **`echo nvt_trigger_update > /tmp/trigger_reboot`**, calls pre-exit hooks, exits to allow platform update/reboot. `ICE_HardwareReset` activates pending update if present else resets.
- **Counters/state:** OAD counters in HW params; denied web-update version files under `/conf`.

**Constraint:** NDFW image format, signed/locked boot chain, and platform update flow must be respected — do not attempt arbitrary flashing.

---

## 9. Filesystem and config surfaces (actionable map)

| Area | Path examples | Notes |
|---|---|---|
| Writable config | `/conf/*` (UBIFS, `apdat0`) | Primary reversible mod surface: `service_menu.txt`, `hotel.tag`, `fti.tag`, PQ/AQ/PCF/PQF/ptf/Dolby, browser/app settings, sqlite DBs, power/ntp/demo flags, coredump flag, etc. **Back up before changes.** |
| Runtime/cache | `/buffer/*` | Browser/cobalt caches, backups, temp assets. |
| Read-only/vendor | `/vendor/*`, `/mtd_apexe/*` | Stock binaries/scripts/resources; replace only via image-level, careful workflows. |
| Temp | `/tmp/*` | Cleared on reboot; trigger files like `trigger_reboot`. |
| Browser/config hooks | `/conf/browser/starturl.txt`, `/conf/browser/dragonfly_server.txt`, `/browser_parameters.txt` (USB import name), `/buffer/browser_home/*`, `/vendor/browser_home/*` | Potential for controlled portal/start-page experiments. |
| Profiles | hw/sw/dev/lang/EFSL/profile artifacts | Managed via USB ops/import-export; format-sensitive. |

---

## 10. Practical modding strategies and tips & tricks

### 10.1 Safe workflow
1. **Keep full backups** (NAND dumps verified; note unreadable `mtd5` and pending SPI NOR in this project state). Store offline.
2. **Prefer `/conf` and sidecar processes** over replacing `aurora.elf` or flashing partitions.
3. **Test over telnet** (`192.168.0.111:23` when jailbreak active; fallback `2323` per project notes). Expect `/tmp` loss on reboot.
4. **Be reversible:** change one thing at a time; keep original files and hashes; know recovery (USB ops, U-Boot volume write, backups).

### 10.2 Custom/sidecar apps (proven path)
- Cross-compile static ARMv7 hard-float binaries for Linux 4.9 userspace; see `hello-world/README.md` and `hello-world/build-docker.sh` (`ubuntu:16.04`, `gcc-arm-linux-gnueabihf`, static).
- Upload/run via telnet. Simple CLI tools are low risk.
- **GUI takeover caveat (`gui-hello-world`):** killing `aurora`/idtv/appmgr to own framebuffer/input can break watchdog/liveness/IPC and cause reboot; no guaranteed on-screen remote-input success without deeper integration. Treat as experimental.

### 10.3 Stock-image customization ideas (by effort/risk)
- **Low:** `/conf` toggles/files (service/hotel/FTI flags, browser start/config where honored), USB-imported supported assets (PQ/PCF/logo/config) via known markers — validate per build.
- **Medium:** sidecar daemons launched from writable hooks (if any safe init hook exists), input-driven tools, network services (respect security exposure).
- **High:** launcher/app-entry integration (Novo/CA/APM string-id handlers, SQLite/portal data sources) — may require binary patching or framework-level changes; map exact data provenance on-device.
- **Very high/risky:** patching `aurora.elf` logic, replacing `ap0/ap1` contents, MTD/bootlogo writes, update chain changes. Requires precise RE, image rebuild/signing awareness, and recovery plan.

### 10.4 Debugging tips
- Use `strings`, symbol/callgraph clues, and Ghidra decomp at cited addresses to trace behavior before changing state.
- Correlate runtime files: `/conf`, `/buffer`, `/vendor/com.nvt.idtv/*`, `nvt.app*.ini`, app logs in `/tmp`/buffers when present.
- `PerformUSBOperations` is a powerful built-in import/export mechanism; understand marker semantics before dropping files on USB.
- Key/input issues: remember UART-based dispatch and internal key ids (e.g. invalid `0x2f1`); remotes map through `mapVestelKey`/`FUN_00761880`.
- Liveness: if experimenting near appmgr/idtv lifecycle, expect watchdog resets; keep a recovery path ready.

### 10.5 “API” surfaces to target (for tooling/mods)
- **Appmgr IPC:** `LIBNAM_APP_SendCommand/Register` (process start/stop/probe semantics observed).
- **Key injection:** `ICE_CallKeyPressFunction` / `ice_SendKey` pathways.
- **USB ops:** `NEBULA_SystemConfigurationPerformUSBOperations` / `NovoSystemConfiguration::performUSBOperations` wrappers and marker files.
- **Profiles/config getters:** extensive `Profile_*` functions (feature gates, customer/product behavior) — influence many code paths.
- **Launcher:** `DemoApp::startLauncherApplication`, Novo item/provider/DB interfaces — primary string-id dispatch points.

---

## 11. Open RE targets (highest value for “new app entries”)

1. **Resolve true runtime `main`/init-array pointer** and full early init ordering; confirm `FUN_00728608` reachability in all boot modes.
2. **Build a key-id/action map:** dump `mapVestelKey` table, fully annotate `FUN_00761880` protocol cases, and trace all `FUN_00761cf8`/dispatcher side effects (including hidden sequences and diagnostic patterns).
3. **App registration population:** trace all `CAStackServer::informApplication*` producers and `CAApplicationManager` consumers on this firmware.
4. **Launcher data provenance:** locate on-device sources of `NovoLauncherItem` lists (SQLite schema/rows in `/conf/sqlite_db`, portal sync caches, `/vendor` resources, `nvt.app*.ini`) to determine data-driven extension.
5. **APM id → executable/URL mapping:** decompile per-mode branches in `ICE_APMRun` and external app start scripts/binaries.
6. **Service/factory menus:** enumerate handlers behind `getServiceMenuInfo`/dialog actions and key combos (beyond USB ops).
7. **`PerformUSBOperations` exhaustive manifest:** resolve every rodata pointer per call site for exact directions/destinations/conditions.

---

## 12. Evidence index (local artifacts)

- Decompiled exports: `/tmp/opencode/ghidra-out/{key,focused,targeted,more,full,deep,small}_decompiled.c`, `selected_*.txt`, `functions.tsv`, `key_strings.txt`, `ptr_strings.txt`, `more_ptrs.txt`, `program_info.txt`.
- Ghidra project: `/tmp/opencode/ghidra-proj/aurora121`.
- Key addresses cited: `_start` `006f3e5c`, bootstrap `0069d950`/`00728608`, `ICE_HardwareInit` `0073bac0`, key dispatch `00763dc0`/`00761880`/`007617c0`/`00761cf8`/`00762aa0`, APM `007842a8`/`00785280`/`00784604`/`007846a0`/`00784740`, USB `0076c488`/`00755988`/`00766354`/`00766e30`/`00768c80`/`00835ef8`, update `007cd4bc`/`007ccab8`/`007cdf64`/`007cde30`, UI `00ab8874`/`00abb17c`/`00cc7074`/`00cecac4`/`00ceeb80`/`00cb7cc4`, etc.

**Reminder:** this is a living RE reference; validate assumptions on-device and keep modifications reversible and non-destructive.
