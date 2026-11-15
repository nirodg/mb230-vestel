# aurora.elf — Ghidra headless decode (MB230 idtv)

**Target:** stock `com.nvt.idtv/aurora.elf` (Vestel/Novatek MB230 “Kylo” main idtv application)  
**Source binary:** extracted from `/media/dorin/more_data/work/mb230-full-backup/mtd12_fs0.bin` → UBI vol `ap0` (SquashFS) → `com.nvt.idtv/aurora.elf`  
**Working copy analyzed:** `/tmp/opencode/rea-targets/aurora_stock.elf` (SHA-256 `c7f1c7b50a68721d25a6704cc7d792e39a6a72c15567794dda1c9cf25626084b`, BuildID `08f88726e6a6d5edbb6b2ad54c008866feba919c`, ~28 MiB, stripped, ELF32 ARM EABI5 hard-float, interpreter `/lib/ld-linux-armhf.so.3`, entry `0x006f3e5d`)

**Analysis method (this pass):** Ghidra **12.1.4 PUBLIC** headless auto-analysis (`analyzeHeadless`, ARM:LE:32:v8, default compiler spec) on the extracted ELF, followed by scripted export of function inventory, key strings/xrefs, and targeted decompilation (Java post-scripts).  
- Program: image base `0x00010000`, analyzed range up to `_elfSectionHeaders::00000527`, **~90,606 functions** recovered by analysis.
- Exports used (generated under `/tmp/opencode/ghidra-out/`, not committed): `program_info.txt`, `functions.tsv`, `key_strings.txt`, `focused_functions_decompiled.c` (45 funcs from key-string referrers), `targeted_decompiled.c` (16 high-value funcs), plus broader key-function decomp attempts.
- REA MCP decompilation was **not** used in-session (Ghidra provider unavailable to the running REA server); this document is grounded in **Ghidra headless decompilation/call-graph evidence** plus prior static findings. Decompiled C is Ghidra’s reconstruction of stripped code (variable/type names and some control-flow details are approximate), but call targets, string refs, constants/paths, and API usage shown are direct analysis results.

> No confidential material (dumps, keys/credentials, HDCP/ROFIX secrets, MAC/serials) is included.

---

## 1. Role and subsystem map (confirmed)

`aurora.elf` is the monolithic **idtv** application orchestrating UI/apps, input, A/V/broadcast, HDMI/CEC, networking, DRM/OTT components, updates, and platform services via extensive Novatek/platform and middleware libraries (DirectFB/fusion/sawman, Mali, GStreamer/FFmpeg, NDAL/TEE/HDCP/NDFW helpers, GLib/soup, SQLite, AVS libs, etc. — see `AURORA_ELF_ANALYSIS.md` §3). It runs under appmgr/privserver with liveness/handshake expectations and expects the stock runtime environment.

Key embedded/version markers (strings): `aurora_trunk_dtv-2020-07-07-15-02-32-dev`; boot-time/appmgr readiness logs `ICE_APM: [BOOT] ICE_APM wait appmgr ready start/done`.

---

## 2. Process lifecycle, suspend/resume, and liveness

### 2.1 Suspend/resume (decompiled)
- **`0073a3a4 idtvSuspend`** (size 0x2de, callers: `0073aaf0 ice_hardware_SuspendToRam`): coordinates suspend path — debug/logging, `LIBNAM_APP_SendCommand(0x204,…)`, `ice_APMCheckStatus`, Wi-Fi/BT/CEC/peripheral handling (WoL/WoW MCU flags, ETH PHY power, Wi-Fi standby/driver actions per dongle type), `ice_PQ_BackupSettings(0)`, `PLAT_SYS_SetMcuWoLOnOff/WoW`, BT eject/wait, bootlogo/STR decode paths, AMP power down (`DEV_AMP_PowerDown`), tuner/NIM/VBI suspend, stops/kills some subsystems (`system` calls observed for process/service teardown in certain modes), OSD plane clear, removable device suspend (guarded), UART IR sim task stop/start controls and UART suspend send, Bluetooth server wait, debug/kernel-msg adjustments, panel-extra timing; loops/delays while waiting for conditions in some cases. Heavy coupling to platform HAL/MCU state.
- **`0073a708 idtvResume`** (size 0x374, callers: `0073aaf0 ice_hardware_SuspendToRam`): reverses/resumes (AMP resume, OSD/DRV update enable/stride/transparency/bootlogo restore, HDCP key restore, Wi-Fi/BT reinit paths, panel/backlight, UART resume, MCU RWDB/init, timers/tasks, `ICE_APMWakeup`/APM state transitions, etc.). (Large body; see `ghidra-out/focused_functions_decompiled.c` @ `0x0073a708`.)
- **`00734358 ICE_HardwareActiveStandby`** / **`0078515c ICE_APMWakeup`**: wake/APM integration points (callers include suspend/resume/APM run paths).

**Implication:** idtv owns deep STR/standby sequencing with MCU, tuner, panel, network, and APM — replacing aurora requires replicating or safely bypassing these contracts.

### 2.2 IPC/liveness indicators (strings/xrefs)
Semaphores and readiness: `mysem_idtv` / `semaphore_idtv` post/open failures, `mysem_appmgr` / `semaphore_appmgr` wait/open failures, appmgr-ready wait logs. Privserver/appmgr identifiers: `COM.NVT.PRIVSERVER(.CB)`. `pkill -f appmgr` appears in multiple flows. Watchdog/task strings present. **Mod risk:** killing/replacing aurora without satisfying handshake/watchdog/appmgr expectations can reboot the device (consistent with observed takeover behavior).

---

## 3. Input and key dispatch

### 3.1 Key event dispatch thread (decompiled)
- **`00763dc0 ice_KeyEventDispatchThread`** (size 0x580, no direct callers recovered as named function callsites in export — typical thread entry; reasons include `ice_KeyEventDispatchThread`, Netflix/RC conversion strings): central loop reading keys via **`00840608 DEV_Uart_GetKey`** (UART/IR path), timing via `PLAT_OS_GetTimeMS`/`PLAT_OS_TimePlus/After`, key mapping/long-press logic via `00761880`, `00761cf8`, `00762aa0 ice_IsButtonLong`, repeat/hotkey/app context checks (`ICE_IsKeyRepeatOn`, `ice_APMGetRunningApp`, `ice_DFB_IsHotKey`, `ICE_APMGetSleepMode`, profile flags e.g. `Profile_IsFairFeaturesEnabled`, `Profile_IsAlexaEmbeddedEnabled`).
- **Behavior highlights (from decomp):** debounced/held-key handling with long-press thresholds; maintains key history/state; special handling for Netflix/APM sleep and hotkeys; digit sequences accumulate in a counter (`*piVar10` logic) and on a specific accumulated value triggers **`0076c488 PerformUSBOperations()`** (USB operations invoked from key-dispatch context). Also interacts with PQ backup, debug/remote-key logging, and dispatches actions through internal handlers (e.g. `0122e3dc`, `FUN_00761cf8`, etc.).
- Related APIs present: `007643ec ICE_KeyRepeatOn`, `007644a4 ICE_KeyRepeatOff`, `007649c8 ICE_CallKeyPressFunction`, `00765384 ice_SendKey`, keyboard/mouse/input-device status handlers, IR init/remote init strings (`ice_InitIrDev`, `ice_InitKeyDev`, `ICE_RemoteInit`), UART IR simulator task hooks seen in suspend/resume.

**Implication:** remote/IR input is processed in-process (UART/DFB/ICE stack) and can trigger system/service actions (including USB ops and app/APM behaviors). “New app entries” or custom UI input handling likely require hooking/understanding this dispatch and focus/APM state.

---

## 4. USB service operations (key mod/recovery surface)

### 4.1 `0076c488 PerformUSBOperations` (decompiled)
- **Signature/size:** `void PerformUSBOperations(void)`, size 0x944.  
- **Callers:** `00f18c84 performUSBOperations`, `00763dc0 ice_KeyEventDispatchThread`.  
- **Callees (selected):** `RmDev_GetLastMountPoint` (00768c80), `FUN_00766354` (file-existence helper), `NonVolatile_CopyUSB` (00755988), `UTILI_JpegIsSupported`, `DEV_MTD_UpdateImage` (00835ef8), `ice_hardware_SyncStrLogo`/sync helpers, `PLAT_ROFIX_UpdateFromDirectory`/backup, `RmDev_UpdateTconFromUSB`/`RmDev_BackupTconFromUSB`, `PLAT_Fact_SyncPanelParametersToXbootData`, `PerformConfBackup` (0073afac), copy helpers `FUN_00766e30`, log/export/packaging helpers, `system`/`ice_system_command`, debug logging.

**High-level logic (from decomp):**
1. Logs entry; obtains last removable mount point (`RmDev_GetLastMountPoint`). Aborts with debug prints if none.
2. **Profile/config import/export (NonVolatile/USB copy):** conditional on presence markers/files on USB (`FUN_00766354` checks), calls `NonVolatile_CopyUSB(mount, …, direction)` to copy profile/config sets (import/export modes observed). Helpers operate on hw/sw/dev/lang/profile and related data.
3. **Device/log/config collection & packaging to USB:** when appropriate markers absent/present per branch, creates timestamped output on USB, iterates known log/state file slots (mutex-protected), reads and aggregates into output files, may tar/gzip bundles (`snprintf` of commands + `system`), removes empty artifacts, syncs.
4. **Boot logo / images:** validates JPEG and can write boot logo to MTD via `DEV_MTD_UpdateImage` (partition selector arg observed as 2 in this path), syncs STR logo (`ice_hardware_SyncStrLogo`), copies related files.
5. **Panel/PQ/EDID/AQ/config/Dolby/browser/other files:** numerous `FUN_00766e30` copy operations between USB and system paths with marker-gated directions (import/download vs export/upload).
6. **ROFIX & credentials area:** `PLAT_ROFIX_UpdateFromDirectory(<usb>/...)` and backup-to-directory paths invoked (sensitive region handling).
7. **TCON:** `RmDev_UpdateTconFromUSB` / `RmDev_BackupTconFromUSB` with marker checks.
8. **Panel params sync:** `PLAT_Fact_SyncPanelParametersToXbootData` on marker.
9. **Finalize:** `sync()`, `PerformConfBackup()`, success logging.

**Resolved rodata markers/paths (from decomp pointer strings, non-exhaustive):**
- Markers/triggers: `/UploadNvram.mb230`, `/DownloadNvram.mb230`, `/DownloadBI.mb230` (boot logo), `/DownloadProfile.mb230`, `/DownloadPQ.mb230`, `/DownloadSpi.mb230`, `/DownloadTcon.mb230`, `/DownloadSerialModelNo.txt`, `/config_update/config_update.txt`, `/enable_coredump`.
- Exports/collections: `/syslog` (USB target area), packaged logs/backup bundles (timestamped naming in code).
- Boot logo/SPI: `/spi/boot_logo.bin`, `/logo.jpg`, `/spi`.
- Sound/AQ/DSP configs: `/sound/AQ.bin`, `/sound/DAP_SE_SetParam.txt`, `/sound/DAPV2_SE_SetParam.txt`, `/sound/DTS_VX_AQ.bin`, `/sound/subw_config_file.txt`, `/sound/ad82586c_config_file.txt` ↔ `/conf/AQ.bin`, `/conf/DAP_SE_SetParam.txt`, `/conf/DAPV2_SE_SetParam.txt`, `/conf/DTS_VX_AQ.bin`, `/conf/subw_config_file.txt`, `/conf/ad82586c_config_file.txt`.
- PQ/panel/Dolby: `/pq/PCF.pcf`, `/pq/PQF.bin`, `/pq/ptf.ptf`, `/pq/dolby.bin`, `/pq/Dolby.cfg` ↔ `/conf/PCF.pcf`, `/conf/PQF.bin`, `/conf/ptf.ptf`, `/conf/dolby.bin`, `/conf/Dolby.cfg`.
- Browser/app config: `/browser_parameters.txt`, `/starturl.txt`, `/default_application.txt`, `/dragonfly_server.txt`, `/iplayer_client.inf`, `/vestel_key.p12`, `/thorium_config.xml`.
- Network/misc: `/ntpserver.txt`, `/forced_ntpserver.txt`, `/demo_commands.txt`, `/conf/power_up.txt`.
- Coredump/debug flag: `/conf/force_enable_coredump`.

(Exact direction, gating, and destination subpaths depend on the specific `FUN_00766e30`/`FUN_00766354` call sites and rodata formats; use as a map for further targeted tracing.)

**Implication:** this is the implementation behind service-menu USB import/export flows (profiles, logs, PQ/panel assets, configs). It is powerful and touches MTD/ROFIX/panel/credentials-adjacent areas — **high-risk** to alter; useful reference for safe, reversible customization via supported file drops on USB.

### 4.2 Related helpers (decompiled/identified)
- **`00755988 NonVolatile_CopyUSB`** (callers include `PerformUSBOperations`, copy-to/from removable): builds commands/paths and copies profile/config artifacts with mutex/locking and sync; handles multiple profile types and directions.
- **`00766354`**: checks `access(<mount>/<name>, F_OK)` (used as marker/file presence test).
- **`00766e30`**: conditional copy helper (USB↔dest) with logging/sync.
- **`00768c80 RmDev_GetLastMountPoint`**: returns current removable mount point under mutex, iterating mount/device structures (widely used by USB/update/file operations).
- **`00835ef8 DEV_MTD_UpdateImage(mtd, src, offsetBlocks)`**: validates image/space, erase+`nandwrite` (via `PLAT_SYS_SystemCall`), optional verify via `nanddump` compare, retries; used for boot/logo and other MTD writes in service paths.

---

## 5. Software update / OAD (Callisto + NDFW)

### 5.1 Activation / reboot into update
- **`007cde30 CallistoActivateNewCode`** (size 0xc4, callers: `00733e38 ICE_HardwareReset`, `007cdf64 upgradeSoftwareFromUSB`): checks `NDFW_GetUpdateStatus`; if update pending — disables backlight, sets MCU LED state, logs, calls `_HW_MCU_SetSecureUpdateMode(1)`, executes **`system("echo nvt_trigger_update > /tmp/trigger_reboot")`** (resolved from rodata; string present), calls `PLAT_SYS_BeforeExitIDTV()` and exits on success path (with error logging fallback). Triggers platform update/reboot flow.
- **`007cdc2c ICE_CallistoIncreaseOADCounter`** (callers include `ICE_CallistoActivateNewCode`/update paths): increments OAD/update counters in HW TV-app params via `_HW_TV_APP_Get/SetParameters` (different counter slots per mode arg).
- **`00733e38 ICE_HardwareReset`**: restores power-up params, shutdown, if `CallistoIsActivateNewCode()` then `CallistoActivateNewCode()` else `PLAT_SYS_Reset()`.

### 5.2 USB software upgrade path
- **`007cd4bc ICE_CallistoCheckUsbToUpgrade`**: finds last mount, checks for upgrade package file on USB (name selected by internal flag/profile), reports availability.
- **`007cdf64 upgradeSoftwareFromUSB`** (size 0x1f8, callers include `009981a0 updateSoftwareFromUsb`, `00768d84 getUpdateFilesFromTFTP`): gets mount, allocates buffer, opens upgrade image from USB, reads in chunks and feeds **`ICE_CallistoWriteBytesToFlash`**, tracks progress, sleeps, on success calls **`CallistoActivateNewCode()`** to finalize/reboot into update.
- **`007ccab8 ICE_CallistoWriteBytesToFlash`** (size 0x50a, callers: `upgradeSoftwareFromUSB`, `010d6ee8 CHIL_CallistoWriteBytesToFlash`): stages/chunks data to temp file, on header/initial chunk sets NDFW update options and parses header (`NDFW_ParserHeader`), validates image set/space (`statfs64`), determines per-image names/lengths (`NDFW_GetImageName/Length`), writes via internal chunk writer and applies images with **`NDFW_UpdateImage`** iterating multi-image packages; manages offsets/state across calls; extensive error/log handling.
- **`007cd5bc ICE_CallistoStartUpgradeSoftwareFromUSB`**: spawns worker thread (`FROST_ThreadCreate`) to perform USB upgrade asynchronously (exposed via Nebula/EASI wrappers `01155f20`/`00967704`).
- **Denied-web-update helpers:** read/write/clear denied-version files under `/conf` (e.g. `ICE_CallistoWrite/ClearDeniedWebSoftwareUpdateVersion*`).

**Implication:** OAD uses NDFW package parsing/update APIs and a controlled reboot trigger (`nvt_trigger_update` + secure mode/exit). Stock upgrade logic is NDFW-aware and multi-image; custom firmware/update flows must respect image format, counters, and boot-chain/signed-partition constraints.

---

## 6. Service, diagnostics, profiles, and PQ/config

- **Service menu/config:** `/conf/service_menu.txt` present (strings/xrefs); service operations exposed through system configuration/Nebula layers and key/USB flows.
- **Profiles:** `Profile_*` API family extensively used (sw/hw/dev/lang profiles, feature flags, hotel/FTI/standby, app/OTT capabilities, telnet/diagnostics toggles etc.) — backed by profile data read from platform/profile store; `Print_Sw_Profile` / `getPQandAQFileNames` style diagnostics aggregate PQ/AQ/PTF/EDID/Dolby version info (e.g. **`007dab44 ICE_ServiceGetPQandAQFileNames`** reads PQ/AQ/PTF/EDID/Dolby version files/APIs and formats report).
- **PQ/AV:** large `ice_PQ_*`, picture control, Dolby/HDR/EDID/VSVDB handling, AQ/PTF integration (PLAT_VAUD/VOUT/EDID helpers).
- **Factory/hotel/FTI:** hotel tags/modes, startup channel/source/volume, FTI/first-time flows, conf backup/restore interactions.

---

## 7. Apps, UI, browser, OTT (high-level from symbols/strings)

- **Key/app dispatch & APM:** `ICE_APM*` (init/run/stop/suspend/wakeup/focus/resource, app hotkeys, Netflix/Amazon/YouTube logout/helpers, sleep/standby integration) — central to launching/switching managed apps.
- **Browser/portal:** browser init/paths (`BROWSER_HOME`, `/buffer/browser_home`, `/vendor/browser_home`), standalone browser flag, HbbTV/HTML app hosting hooks.
- **OTT/integrations:** Netflix, Amazon/Prime Video/Alexa (AVS libs linked), Cobalt/YouTube paths; DIAL/DLNA/Miracast/WFD components linked.
- **Nebula/EASI/C++ app frameworks:** many `CAApplicationManager`, `Nebula*`, `EASI*`, `Novo*` symbols indicate large C++ UI/application framework layers (menus, dialogs, settings, channel/app management) — potential “app entry” points live here but require deeper per-class RE to modify safely.
- **External/debug launch hooks (from prior repo evidence):** scripts/ini in `/vendor` and `/conf` (e.g. `run_aurora.sh`, debug ini, `remote.txt`/dev run modes) can alter launch in supported dev configurations.

---

## 8. Modding-relevant takeaways (evidence-backed)

1. **Liveness is mandatory:** suspend/resume, appmgr/privserver/semaphores, watchdog, and MCU coordination are integral — custom replacements must satisfy or coexist without breaking these contracts.
2. **USB operations are a built-in control plane:** `PerformUSBOperations` (callable from service flows and key-dispatch sequences) imports/exports profiles/configs/logs and can write MTD/ROFIX/panel assets — powerful for recovery/config mods but easy to brick/misconfigure; prefer reversible `/conf`/supported drops.
3. **Update path is NDFW + trigger:** USB upgrade streams into `ICE_CallistoWriteBytesToFlash` (NDFW parse/update) and activates via `CallistoActivateNewCode` → `nvt_trigger_update` + secure mode/exit. Respect NDFW format and signed/locked boot components.
4. **Input is centralized:** `ice_KeyEventDispatchThread` (UART key source) mediates long-press/repeat/APM context and can invoke privileged actions (e.g. USB ops). Custom UX/input remap or hidden-entry triggers intersect here.
5. **Config surface:** `/conf` (rw) holds service/hotel/FTI/flags, PQ/AQ/PCF/Dolby, browser/app state — primary low-risk customization area when backed up.
6. **Deep “new app entries”:** likely in Nebula/EASI/app-manager/UI layers (large C++ surface) plus APM/portal registration; requires targeted decompilation of those modules/classes and resource/manifest understanding beyond this pass.
7. **Do not touch:** signed boot chain components, DRM/HDCP/ROFIX/credentials/keys, or irreversible MTD writes without verified images and full backups.

---

## 9. Startup, hardware init, and main loop (decompiled)

- **`006f3e5c _start`** → calls **`__libc_start_main`** with program entry/main (rodata-resolved function pointer) and init/fini handlers, then `abort` on return. The actual `main` symbol/address is resolved via `.init_array`/libc startup conventions (further tracing of the rodata pointer yields the application entry; multiple `main`-named symbols exist in the binary image, typical of linked components/static libs, so entry resolution should be correlated with runtime/init behavior).
- **`0073bac0 ICE_HardwareInit`** (very large, ~4 KB; caller e.g. early init path): performs broad platform bring-up — profile/board/feature queries, boot-logo/STR and special-key/exit-type handling, power-up/fast-boot parameter restore, MCU/RC init, EDID order, panel/VOUT/VUI/DSP/NIM/audio/video/pq/callisto/DRM/CEC/network/USB/storage related initialization, debug/console/signal setup hooks, environment/file checks, sync of state to xboot/MCU where applicable. Central to making the rest of aurora functional.
- **`00746f94 _ice_start_mainLoop`**: creates a GLib main loop (`g_main_loop_new`) and spawns a thread to run it for media/player contexts (used by media player select/play/get-details paths).

## 10. APM (Application/Process Manager) and app lifecycle (decompiled)

- **`007842a8 ICE_APMInit`** (caller `0099c22c APMInit`): initializes APM state/callback structs, waits for appmgr/readiness, prepares brand/software/version context files under writable areas (via `PLAT_PRIVCTRL_System`/fopen/fwrite), registers APM (`ice_APM_Register`), creates worker/monitor tasks (`PLAT_OS_CreateTask`), registers NPC/PQ APM callback, sets ready flags.
- **`00785280 ICE_APMRun`** (large; caller `0099c918 run`): core app-run/transition logic by app/mode id. Manages OSD/plane/alpha/video-audio path switching, wake/stop/probe/start of app processes (`ice_APM_Probe/Start/StopProcess`), DIAL/URL handling, PQ/picture restore, and input/focus state.
  - **Resolved process/launch identifiers (rodata):** case paths reference managed app/process names such as `netflix` (`01254ad3`), `amazon` (`01262017`), `youtube` (`01476f48`), and `youtube_test` (`01260d32`).
  - **Resolved launch/URL fragments:** e.g. Netflix additional-data URL (`source_type=19&additionalDataUrl=.../apps/Netflix/dial_data...`), YouTube menu/remote DIAL-style launches (`launch=menu|remote&additionalDataUrl=.../apps/YouTube/dial_data...`), recommendation params (`youtube_recommendation_video_id|channel_id|playlist_id`), and `dialLaunch` handling — showing APM coordinates process start with dial/URL context for OTT apps.
- **`00784094 ICE_APMHandleKeypress`**: routes keypresses into APM/focus context (hotkey/app-aware handling).
- **Other APM APIs:** `ICE_APMStop/Suspend/Wakeup`, focus/resource acquire/lose, Netflix/standby flags, logout helpers (Amazon/YouTube/Netflix), language/country, sleep mode — collectively control app foregrounding and power/UX transitions.

**Implication for “new app entries”:** adding a first-class app in stock UI likely requires integration at APM/app-registration and UI/launcher layers (process start command/URL, focus/resource handling, hotkeys), not just placing binaries.

## 11. UI launcher and app registration (decompiled, C++ framework)

- **`00ab8874 CAApplicationManager::registerApp`** (caller `00abb17c informApplicationAdd`): sanity-checks and stores an app record in an internal table (indexed by count at `this+0x100`, entry stride `0x10`) containing type/id, a 16-bit field, and an app info/string copied to `UString` (capacity up to 0x10 entries observed in guard). **`00ab88e8 deregisterApp`** removes entries (not shown here in full). This is a concrete in-process app registry used by the Cabot/Nebula UI stack.
- **`00cc7074 DemoApp::startLauncherApplication(UString const&, bool)`** (many UI callers: open-selected-app/menu/button/AVS/ODC paths): resolves the selected app identifier string and dispatches to handlers.
  - **Resolved id/match strings (rodata):** checks availability and matches/substrings against **`netflix.swf`** (→ `handleNetflixRequest`), **`amazon.swf`** (→ `handleAmazonRequest`), **`youtube.swf`** and **`youtube_recommendation`** (Cobalt/profile-gated → `handleYoutubeRequest` with mode/URL context). Trace strings observed: “Open Netflix Application”, “Open Amazon Prime Application”, “Open Youtube Application from Launcher/Recommendation”.
  - **Fallback/on-demand:** resolves content/launcher item or browser/ODC context → `launchOnDemandContentWithContext` or posts UI key/message to framework/browser path. Uses `Profile_IsCobaltSupportEnabled` and connectivity/Novo configuration checks. This is a key **string-id → launch-handler** junction in the stock launcher flow.
- **Novo launcher framework:** numerous `NovoLauncherItem`/launcher-manager/data-provider and selection/start helpers (`startLauncherApplication`, `initialiseLauncherSourceItems`, `getSelectedLauncherItemId`, etc.) manage launcher UI state and invoke launch.

**Implication for “new app entries”:** feasible customization points include (a) launcher item/config sources feeding `startLauncherApplication` with recognized ids, (b) extending handler/id matching and backing app start (APM/process/URL), and/or (c) `CAApplicationManager` registration — all require understanding expected id strings, resources, and lifecycle. Where ids/assets are data-driven (configs/resources on `/vendor` or `/conf`), config-level extension may be possible; otherwise binary patching or rebuilt UI components are needed (validate per-firmware).

## 12. Input helpers and dispatch glue (decompiled)

- **`00761880`**: maps raw/translated key data to internal key code/long-press timing parameters (table/lookup-driven; returns success and outputs duration/code info used by dispatcher).
- **`00761cf8`**: key action handler/dispatcher invoked from the key thread for resolved key events (large switch/logic; integrates with UI/APM/actions).
- **`00762aa0 ice_IsButtonLong`**: determines long-press state given key, repeat state, and threshold timing.
- **`0076330c ice_Netflix_IR_Callback`**: Netflix-specific IR/key callback path coordinating with APM/sleep/hotkey behavior.
- **`007643ec ICE_KeyRepeatOn` / `007644a4 ICE_KeyRepeatOff` / `007649c8 ICE_CallKeyPressFunction` / `00765384 ice_SendKey`**: repeat state and synthetic/injected key delivery helpers.

Together with **`00763dc0 ice_KeyEventDispatchThread`** (§3.1), these form the end-to-end path from UART/IR input to app/UI actions and privileged triggers.

## 13. USB/profile helpers (additional decompiled detail)

- **`00755988 NonVolatile_CopyUSB(mount, name, direction)`**: mutex-guarded copy of profile/config sets between USB mount and internal storage using constructed shell commands (`snprintf`/`ice_system_command`), with pre/post sync and cleanup; direction selects import vs export behavior for hw/sw/dev (and related) profile artifacts.
- **`0073afac PerformConfBackup`**: backs up `/conf`-related state (used at end of `PerformUSBOperations` and elsewhere) to preserve configuration.
- **`00766354` / `00766e30`**: marker existence check and conditional file copy helpers used per-file in `PerformUSBOperations` (rodata-resolved paths/names select specific PQ/AQ/PCF/Dolby/browser/panel/tuner/config targets).

## 14. Artifacts, coverage, and next steps

- **Ghidra project (local, not committed):** `/tmp/opencode/ghidra-proj/aurora121` (analyzed `aurora_stock.elf`).
- **Exports (local, not committed):** `/tmp/opencode/ghidra-out/` — `program_info.txt`, `functions.tsv` (~90k), `key_strings.txt`, `focused_functions_decompiled.c`, `targeted_decompiled.c`, `more_decompiled.c`, plus ad-hoc extracts.
- **Coverage:** headless auto-analysis of the full binary; decompiled evidence now includes startup/lifecycle hooks, `ICE_HardwareInit`, APM init/run/keypress, input dispatch and helpers, USB operations and helpers, Callisto/NDFW OAD chain, and key UI/app-registry/launcher functions (`CAApplicationManager::registerApp`, `DemoApp::startLauncherApplication`). Large Nebula/EASI/Novo/CA C++ surfaces remain only partially decompiled.
- **Recommended follow-ups (targeted Ghidra):** (a) resolve `main`/init-array entry and appmgr/privserver/semaphore/watchdog contract in code, (b) dump/resolve rodata string tables for `PerformUSBOperations` and key-dispatch action tables to exact file/key manifests, (c) enumerate all `startLauncherApplication` id matches and their backing handlers/start commands (and launcher item/config sources on filesystem), (d) trace APM app ids/process names/URLs and `CAApplicationManager` population sites, (e) decompile service-menu command handlers and factory gates, (f) validate changes only via reversible `/conf`/sidecar experiments with full backups.

This document, together with `AURORA_ELF_ANALYSIS.md`, provides a Ghidra-backed decode of the stock `aurora.elf` sufficient to guide informed, reversible customization and to target further RE where native app-entry/UI modifications are required.