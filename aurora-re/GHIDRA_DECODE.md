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

## 9. Startup, hardware init, and bootstrap chain (decompiled)

- **`006f3e5c _start`** → `__libc_start_main(...)` → `abort` on return (entry/main resolved via libc/init linkage).
- **`0069d950 main`**: argument handling for `-v/--version` (prints SVN URL/revision via `getSVNURL`, `getSVNGlobalRevisionInfo`) and `-h/--help`/usage; in normal execution path calls **`FUN_00728608`**.
- **`00728608` (primary bootstrap, caller `0069d950`)**:
  1. `ICE_InitialiseSystemMemory()` (`00754a2c`, registers signal handlers `debugRegisterSignalHandlers`).
  2. Stores PID (`getpid`).
  3. `ICE_DebugInit()` (`007298bc`, waits for debug readiness, registers debug commands).
  4. `profileManagerStart()` (`00728674`: `ProfileManager::getInstance`, attaches multiple `ROMProfile` sources).
  5. `FROST_DebugStartConsole()` (`00729248`: console/testtool tasks/commands as enabled).
  6. `ICE_HardwareInit()` (`0073bac0`).
  7. `ICE_InitRTC()` (`0076d4c0`: `PLAT_OS_SyncRTCFromSTBC`).
  8. `eclipseStart()` (`009217b8`: `preemptiveNetworkInit`, `new StandardSettop`, `StandardSettop::initialise`).
  9. Infinite `FROST_Sleep(...)` loop.
- **`0073bac0 ICE_HardwareInit`** (very large): broad platform bring-up (profiles/board flags, STR/boot/special-key/exit handling, power-up restore, MCU/RC/EDID, panel/VOUT/DSP/NIM/A/V/PQ/Callisto/DRM/CEC/network/USB/storage, debug hooks, env/file/tag checks, xboot/MCU sync).
- **`00746f94 _ice_start_mainLoop`**: GLib main loop in a thread for media/player contexts.
- **Note:** another `main` symbol exists (`006a0ac4`, `CECInterface::main`) in a different C++ context.

## 10. APM (Application/Process Manager) and app lifecycle (decompiled)

- **`007842a8 ICE_APMInit`** (caller `0099c22c APMInit`): waits appmgr readiness, initializes APM state/callbacks, prepares brand/software/version context (writable files), `ice_APM_Register` (`00784254` → `LIBNAM_APP_Register`), creates worker tasks, registers NPC/PQ APM callback.
- **`00785280 ICE_APMRun`** (caller `0099c918 run`): app/mode transitions — OSD/plane/alpha and A/V switching, `ice_APM_Probe/Start/StopProcess`, DIAL/URL handling, PQ restore, input/focus coordination.
  - **Resolved process names (rodata):** `netflix`, `amazon`, `youtube`, `youtube_test`.
  - **Resolved URL/context fragments:** Netflix/YouTube dial `additionalDataUrl` paths, `launch=menu|remote`, `dialLaunch`, `youtube_recommendation_video_id|channel_id|playlist_id`.
- **IPC process control (appmgr via `LIBNAM_APP_SendCommand`):**
  - `ice_APM_StartProcess` (`00784604`): cmd `0x106`, payload name/args, type 2.
  - `ice_APM_StopProcess` (`007846a0`): cmd `0x106`, type 1, stop flag.
  - `ice_APM_ProbeProcessStatus` (`00784740`): cmd `0x104`, returns status.
- **Other APM APIs:** `ICE_APMHandleKeypress` (`00784094`), `ICE_APMStop/Suspend/Wakeup`, focus/resource, Netflix/Amazon/YouTube helpers, country/language/sleep/hotkey logic.

**Implication:** “new app entry” behavior in stock stack depends on launcher/UI ids, APM run/start/stop/focus, and appmgr IPC — not binary placement alone.

## 11. UI launcher and app registration (decompiled, C++ framework)

- **`00ab8874 CAApplicationManager::registerApp`** (caller `00abb17c informApplicationAdd` via `CAStackServer`): in-process table at `this+0x100`, stride `0x10`, guard/capacity 0x10 in checked path; stores type, 16-bit field, copied `UString` app info. **`00ab88e8 deregisterApp`** removes entries.
- **App availability/start notifications (CI/MHEG/HbbTV paths):** `CAStackServer::informApplicationAvailable` builds async MHEG launch message to EASI control (subtitle/profile context); `ApplicationMMISession::informApplicationStart` → `INCA_MHEGApplicationStart` / `INCA_HbbTVApplicationStart`.
- **`00cc7074 DemoApp::startLauncherApplication(UString const&, bool)`**: string-id dispatch (resolved rodata) — `netflix.swf` → `handleNetflixRequest`, `amazon.swf` → `handleAmazonRequest`, `youtube.swf` / `youtube_recommendation` (Cobalt/profile-gated) → `handleYoutubeRequest`; fallback to on-demand/browser/content launch or UI message posting.
- **UI open flow:** `FullScreenMarketDialog::openSelectedApp` (`00cecac4`) / `FullScreenPortalDialog::openSelectedApp` (`00ceeb80`) resolve selected `NovoLauncherItem` (id/url/name), set logging/CID/input context, invoke `startLauncherApplication`.
- **Novo launcher framework:** `NovoLauncherItem`/manager/data-provider and DB-backed sources (`SqliteLauncherDatabaseAdapter` insert/update/remove/update-all in symbol/string evidence), portal/market sync and recommendation/settings flows; launcher UI assets/strings present. `novoLauncherManager()` accessor used widely.

**Implication:** extension points are (a) data/config sources feeding launcher items/ids, (b) id→handler/start mapping, (c) CA/appmgr registration and lifecycle — feasibility depends on per-firmware data provenance vs hardcoded handlers.

## 12. Input, key decode, and dispatch glue (decompiled)

- **`00763dc0 ice_KeyEventDispatchThread`**: reads `DEV_Uart_GetKey`, maps raw codes via `FUN_00761880`, applies repeat/long-press (`ice_IsButtonLong` `00762aa0`, `ice_dispatch_long_button`, `ICE_IsKeyRepeatOn`) and hotkey/APM/profile gating (`ice_DFB_IsHotKey`, `ICE_APMGetRunningApp/SleepMode`, feature flags), dispatches via `FUN_00761cf8` and related handlers; logs PQ/key state in some paths.
  - **Hidden USB-ops trigger (evidence):** for internal digit-key range `0x200–0x209`, dispatcher processes sequence accumulation (`FUN_0122e3dc(acc*10 + (key-0x200), DAT_007643c4)` with `DAT_007643c4=1000000`) and, when accumulator/global at `DAT_007643c0` equals **`472569`** (`DAT_007643c8`), calls **`PerformUSBOperations()`** then resets accumulator. Non-matching key handling resets sequence (keys in `0x9d0–0x9d9` treated specially in branch logic). Distinct from service-menu `MENU 4725` access (`RESEARCH.MD`); validate on-device.
- **`00761880`**: decodes raw key payloads across protocol/type cases (incl. system/address extraction and validation against stored RC config) and maps command via `mapVestelKey`; returns `0x2f1` for invalid/unmapped.
- **`007617c0 mapVestelKey`**: table lookup mapping RC command byte to internal key id (returns `0x2f1` if not found); optional debug print gated by profile.
- **`00761cf8`**: routes resolved key events — suspend-to-RAM on specific `0x21f` state, DVD-source key filtering, hotel/fair-feature/Netflix gating, diagnostic pattern checks on `0x21f/0x9ef`, forwards to Netflix callback or `ice_SendKeyToMw`; integrates with backlight/app-running state.
- **Helpers:** `ICE_KeyRepeatOn/Off` (`007643ec/007644a4`), `ICE_CallKeyPressFunction` (`007649c8`), `ice_SendKey` (`00765384`), `ice_Netflix_IR_Callback` (`0076330c`), remote init/UART IR simulator hooks.

## 13. USB/profile helpers, service menu, and config surfaces

- **`00755988 NonVolatile_CopyUSB`**: mutexed, command-based hw/sw/dev/lang profile copy (USB↔internal) with sync/cleanup.
- **`0073afac PerformConfBackup`**: backs up `/conf`-related state (end of USB ops and other flows).
- **`00766354` / `00766e30`**: marker existence and conditional copy helpers for `PerformUSBOperations` targets.
- **Service menu flow:** `DemoApp::onShowServiceMenu` → `DemoApp::doMenuService` (`00cb7cc4`) → `ServiceMenuDialog` (SVG/MyMenu/General dialog stack). Handles modal actions/module state; can invoke USB operations via `NovoSystemConfiguration::performUSBOperations` with DVR/removable-device checks and prompts/auto-message flows. Guards: `isServiceMenuProfilePasscodeAvailable`, `controlServiceMenuPwd`, Philips variants/timers, capture-pwd flows; info/report via `getServiceMenuInfo`.
- **Config/DB hints (strings):** `/conf/service_menu.txt`, `/conf/sqlite_db/settingsDB.db` (and related backup/copies), browser config paths (`/conf/browser/starturl.txt`, `/conf/browser/dragonfly_server.txt`), USB-side browser/app config names imported by `PerformUSBOperations`.

## 14. Artifacts, coverage, and next steps

- **Ghidra project (local, not committed):** `/tmp/opencode/ghidra-proj/aurora121`.
- **Exports (local, not committed):** `/tmp/opencode/ghidra-out/` — `program_info.txt`, `functions.tsv` (~90k), `key_strings.txt`, `ptr_strings.txt`, `more_ptrs.txt`, `focused_functions_decompiled.c`, `targeted_decompiled.c`, `more_decompiled.c`, `full_decompiled.c`, `deep_decompiled.c`, `small_decompiled.c`, `selected_*.txt`, plus logs.
- **Coverage (added this pass):** bootstrap chain (`0069d950`→`00728608` and callees), key dispatch internals and hidden USB sequence constants, key decode/map, APM IPC start/stop/probe, service-menu `doMenuService`/dialog wiring, launcher open-selected flows, CA/CI/MHEG/HbbTV app notification paths, additional pointer/string resolution.
- **Comprehensive modding reference:** see `aurora-re/AURORA_MODDING_REFERENCE.md` (APIs/surfaces, USB manifest, app/launcher model, risks, tips & tricks).
- **Recommended follow-ups:** (a) dump `mapVestelKey` table and fully enumerate decoded key ids/actions, (b) trace launcher/Novo item provenance on-device (SQLite schema/rows, portal caches, vendor resources), (c) map APM run modes to concrete start commands/binaries, (d) resolve `FUN_0122e3dc` accumulator semantics precisely and other hidden sequences, (e) enumerate `startLauncherApplication` handlers and on-demand/browser launch parameters, (f) full service-menu/factory handler/action map, (g) resolve remaining `PerformUSBOperations` per-site direction/conditions, (h) validate all mod hypotheses reversibly on-device.

This document, together with `AURORA_ELF_ANALYSIS.md` and `aurora-re/AURORA_MODDING_REFERENCE.md`, provides a Ghidra-backed decode of the stock `aurora.elf` to guide informed, reversible customization and to target further RE where native app-entry/UI modifications are required.