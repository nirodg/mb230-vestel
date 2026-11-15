# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A reverse-engineering research project for the Vestel **17MB230** TV mainboard (Novatek NT72671/NT72673 SoC, 4× Cortex-A7, ARMv7 32-bit, Linux 4.9 "Kylo" OS with a Cobalt/"Picasso" UI). The target device is a Horizon 50HL7530U/B. Most of the repo is documentation; the code is small Python tooling built to analyze data pulled from the TV.

- `README.md`: goals (debloat, root/SSH, custom apps), the Medion MD 30010 firmware downgrade procedure, and what does and doesn't work after downgrading.
- `RESEARCH.MD`: the main findings. It covers the service-menu **USB Operations** dump/upload mechanism (`MENU 4 7 2 5`, `Download*.MB230` folders), the EFSL profile format, the language profile, PTF fields, and Cobalt debug flags.
- `ARCHITECTURE.md`: SoC, boot chain (XBOOT → DDRCFG → SECOS → U-Boot 2016.07 → kernel → SquashFS-in-UBI), and the NAND partition table taken from `kylo_usb_update.scr`. Facts are cited from the firmware (DTS, uImage headers). Keep that standard: don't add claims that can't be traced to firmware evidence.

## Running the tools

Python 3, no build system, no tests, no linter config.

```bash
# Tkinter GUI inspector for a USB dump directory (standard library only)
python3 mb230_inspector.py --dir /path/to/dump

# OIPF API explorer: Flask server that the TV's built-in browser loads.
# Binds 0.0.0.0:80, so it needs root. Appends JSON lines to device_research.log in the CWD.
sudo python3 browser/app.py
```

## Code architecture

**`mb230_inspector.py`** is one self-contained file (~1900 lines). Keep it free of dependencies outside the standard library, as its docstring promises. Its layout:
- Format parsers, each a `parse_*(path)` function that returns a dataclass: `parse_ptf` (panel timing, text key/value), `parse_edid` (base block plus CTA-861 extensions), `parse_efsl` (hw/sw profiles: 32-byte header with magic `EFSL`, then 20-byte entries of type/subtype/value/data_offset/crc32), and `parse_langprofile` (null-terminated UTF-8 strings).
- `PTF_FIELD_DESCRIPTIONS`, `PTF_RISKY_FIELDS` and `PTF_SAFE_FIELDS` annotate panel-timing fields. The "risky" ones (PLL, totals, GPIOs, LVDS format) can blank the panel if changed.
- `discover_files()` sorts the files in a dump directory into categories **by filename pattern** (`*.ptf`, `edid*`, `*hwprofile*`, `*swprofile*`, `*langprofile*`, `.pcf`/`pqf`, audio `.bin` keywords, and so on). To support a new file type, add both a pattern here and a sidebar view in `MB230Inspector`.
- `MB230Inspector(tk.Tk)` is the GUI, with a sidebar per category and a viewer for each format.

**`parsers/efsl_parser.py`** is an unused fragment: it has no imports and nothing imports it. The live EFSL parser is the one inside `mb230_inspector.py`. Keep the two in sync if you touch either, or fold the fragment into the main file.

**`browser/app.py`** is a Flask app with two routes. `GET /` serves an inline HTML/JS dashboard (`DASHBOARD_HTML`) whose buttons call OIPF/HbbTV APIs in the TV browser. Each result is `POST`ed to `/log`, which prints it to the console and appends it to `device_research.log`. The JS has to run on the TV's old embedded browser, so stick to conservative ES5-style code.

## Repo hygiene

- Firmware images (`*.zip`, `kylo_usb_update.bin/.scr`, about 200+ MB) and TV dumps must not be committed. There is no `.gitignore` yet, and `MD30010_Firmware_Full_Update_DE.zip` is currently untracked in the working tree.
- `parsers/__pycache__/` was committed by mistake.
- Dumps can contain device secrets (HDCP keys, PlayReady/Marlin DRM material, MAC/serials). Don't paste their contents into docs.
