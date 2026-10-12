#!/usr/bin/env python3
"""
MB230 Config Inspector
======================
A GUI tool for parsing and inspecting files from an MB230 (Vestel/Novatek)
TV dump.

Features:
  - Sidebar navigation for different file types
  - PTF parser: decodes all panel timing parameters with descriptions
  - EDID parser: decodes base + CTA-861 extension blocks
  - EFSL parser: decodes hwprofile/swprofile entry tables (20-byte entries)
  - Language profile parser: extracts all UTF-8 strings with offsets
  - XML viewer: tree view + pretty-printed code + raw
  - Text file viewer: plain content
  - Binary viewer (PQ/Audio/Other): summary + extracted strings + hex

Usage:
  python3 mb230_inspector.py [--dir /path/to/dump]

No external dependencies — uses only the Python standard library.
"""

import os
import sys
import struct
import zlib
import hashlib
import argparse
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from collections import Counter


# =============================================================================
# PTF PARSER
# =============================================================================

PTF_FIELD_DESCRIPTIONS = {
    "u8PanelID": "Panel identifier (0xFF = generic/unset)",
    "b8Mode50Hz": "Enable 50 Hz refresh mode (0=disabled, 1=enabled)",
    "u8Panel": "Panel profile index",
    "au8Name": "Panel timing generator name",
    "u8PanelType": "Panel type variant",
    "u8Tcon": "TCON type (2 = Novatek internal VX1 TCON)",
    "u8TconType": "TCON sub-type",
    "Revision": "File revision string",
    "b8DualPixelOutput": "Dual-pixel LVDS output (required for 4K)",
    "enLvdsFormat": "LVDS interface format",
    "b8ABSwap": "A/B LVDS channel swap",
    "b8ChannelSwap": "LVDS channel order swap",
    "b8RBSwap": "Red/Blue channel swap",
    "b8HFlip": "Horizontal flip",
    "b8VFlip": "Vertical flip",
    "u8DitheringBit": "Dithering (8-bit to 10-bit expansion)",
    "b8FrameSyncEnable": "Frame sync enabled (prevents tearing)",
    "u8FrameSyncMode": "Frame sync mode",
    "u8MISC": "Miscellaneous flags",
    "b8Blinking": "Panel test blinking (should be 0)",
    "b8OutputPanelFHD": "Output FHD instead of UHD",
    "u16LVDSPhase": "LVDS clock phase",
    "u16LVDSPhase_PortA": "LVDS clock phase, Port A",
    "u16LVDSPhase_PortB": "LVDS clock phase, Port B",
    "u16VX1PreEmphasisG1": "VX1 LVDS pre-emphasis group 1",
    "u16VX1PreEmphasisG2": "VX1 LVDS pre-emphasis group 2",
    "u16VX1PreEmphasisG3": "VX1 LVDS pre-emphasis group 3",
    "u16VX1SwingG1": "VX1 LVDS swing group 1",
    "u16VX1SwingG2": "VX1 LVDS swing group 2",
    "u16VX1SwingG3": "VX1 LVDS swing group 3",
    "u16PanelPowerOnDelay1": "Panel power-on delay 1 (ms)",
    "u16PanelPowerOnDelay2": "Panel power-on delay 2 (ms) - usually long, for LVDS lock",
    "u16PanelPowerOFFDelay1": "Panel power-off delay 1 (ms)",
    "u16PanelPowerOFFDelay2": "Panel power-off delay 2 (ms)",
    "u16PanelPowerGPIO": "GPIO pin for panel power enable",
    "u16PanelBackLightGPIO": "GPIO pin for backlight enable",
    "b8PanelPowerInvert": "Invert panel power signal",
    "b8BacklightPowerInvert": "Invert backlight signal",
    "u16BackLightLevel": "Default backlight level (0-100)",
    "u16BacklightFreq": "Backlight PWM frequency (Hz)",
    "b8PWMDutyInv": "Invert PWM duty cycle",
    "b8LocalDIMControl": "Local dimming control (0=disabled)",
    "stMode50Hz.u16Width": "50Hz: Active horizontal pixels",
    "stMode50Hz.u16Height": "50Hz: Active vertical lines",
    "stMode50Hz.u16TypHTotal": "50Hz: Total horizontal pixels (incl. blanking)",
    "stMode50Hz.u8HSyncWidth": "50Hz: HSync pulse width (pixels)",
    "stMode50Hz.u16HSyncBackPorch": "50Hz: Horizontal back porch (pixels)",
    "stMode50Hz.u16HSyncStart": "50Hz: HSync start position",
    "stMode50Hz.u16TypVTotal": "50Hz: Total vertical lines (incl. blanking)",
    "stMode50Hz.u8VSyncWidth": "50Hz: VSync pulse width (lines)",
    "stMode50Hz.u16VSyncBackPorch": "50Hz: Vertical back porch (lines)",
    "stMode50Hz.u16VSyncStart": "50Hz: VSync start position",
    "stMode50Hz.u16PLL": "50Hz: Pixel clock PLL (in 10 kHz units)",
    "stMode60Hz.u16Width": "60Hz: Active horizontal pixels",
    "stMode60Hz.u16Height": "60Hz: Active vertical lines",
    "stMode60Hz.u16TypHTotal": "60Hz: Total horizontal pixels (incl. blanking)",
    "stMode60Hz.u8HSyncWidth": "60Hz: HSync pulse width (pixels)",
    "stMode60Hz.u16HSyncBackPorch": "60Hz: Horizontal back porch (pixels)",
    "stMode60Hz.u16HSyncStart": "60Hz: HSync start position",
    "stMode60Hz.u16TypVTotal": "60Hz: Total vertical lines (incl. blanking)",
    "stMode60Hz.u8VSyncWidth": "60Hz: VSync pulse width (lines)",
    "stMode60Hz.u16VSyncBackPorch": "60Hz: Vertical back porch (lines)",
    "stMode60Hz.u16VSyncStart": "60Hz: VSync start position",
    "stMode60Hz.u16PLL": "60Hz: Pixel clock PLL (in 10 kHz units)",
}

PTF_RISKY_FIELDS = {
    "stMode50Hz.u16TypHTotal", "stMode50Hz.u16TypVTotal", "stMode50Hz.u16PLL",
    "stMode60Hz.u16TypHTotal", "stMode60Hz.u16TypVTotal", "stMode60Hz.u16PLL",
    "u16PanelPowerGPIO", "u16PanelBackLightGPIO",
    "u16LVDSPhase", "u16LVDSPhase_PortA", "u16LVDSPhase_PortB",
    "enLvdsFormat", "b8DualPixelOutput",
}

PTF_SAFE_FIELDS = {
    "u16BackLightLevel", "u16BacklightFreq",
    "u16PanelPowerOnDelay1", "u16PanelPowerOnDelay2",
    "u8DitheringBit", "b8FrameSyncEnable", "b8Mode50Hz",
}


@dataclass
class PTFEntry:
    key: str
    value: str
    description: str = ""
    risk: str = "unknown"


@dataclass
class PTFData:
    path: str
    entries: List[PTFEntry] = field(default_factory=list)
    timing_modes: Dict[str, Dict[str, PTFEntry]] = field(default_factory=dict)
    raw_lines: List[str] = field(default_factory=list)


def parse_ptf(path: str) -> PTFData:
    data = PTFData(path=path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    data.raw_lines = lines
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key_part, value_part = stripped.split("=", 1)
        key = key_part.strip()
        value = value_part.strip()
        if "//" in value:
            value = value.split("//")[0].strip()
        if not key:
            continue
        if key in PTF_RISKY_FIELDS:
            risk = "risky"
        elif key in PTF_SAFE_FIELDS:
            risk = "safe"
        else:
            risk = "unknown"
        entry = PTFEntry(key=key, value=value,
                         description=PTF_FIELD_DESCRIPTIONS.get(key, ""),
                         risk=risk)
        data.entries.append(entry)
        if "." in key:
            mode = key.split(".", 1)[0]
            data.timing_modes.setdefault(mode, {})[key] = entry
    return data


# =============================================================================
# EDID PARSER
# =============================================================================

EDID_MANUFACTURER_IDS = {
    "VES": "Vestel", "SAM": "Samsung", "LGD": "LG Display",
    "AUO": "AU Optronics", "CMO": "Chi Mei Optoelectronics",
    "INL": "Innolux", "BOE": "BOE", "HSD": "HannStar",
    "SEC": "Samsung Electronics",
}

EDID_VIDEO_FORMATS = {
    1: "640x480 @ 60 Hz (4:3)", 2: "720x480 @ 60 Hz (4:3)",
    3: "720x480 @ 60 Hz (16:9)", 4: "1280x720 @ 60 Hz (16:9)",
    5: "1920x1080i @ 60 Hz (16:9)", 6: "1440x480i @ 60 Hz (4:3)",
    7: "1440x480i @ 60 Hz (16:9)", 16: "1920x1080 @ 60 Hz (16:9)",
    17: "720x576 @ 50 Hz (4:3)", 18: "720x576 @ 50 Hz (16:9)",
    19: "1280x720 @ 50 Hz (16:9)", 20: "1920x1080i @ 50 Hz (16:9)",
    21: "1440x576i @ 50 Hz (4:3)", 22: "1440x576i @ 50 Hz (16:9)",
    31: "1920x1080 @ 50 Hz (16:9)", 32: "1920x1080 @ 24 Hz (16:9)",
    33: "1920x1080 @ 25 Hz (16:9)", 34: "1920x1080 @ 30 Hz (16:9)",
    93: "3840x2160 @ 24 Hz (16:9)", 94: "3840x2160 @ 25 Hz (16:9)",
    95: "3840x2160 @ 30 Hz (16:9)", 96: "3840x2160 @ 50 Hz (16:9)",
    97: "3840x2160 @ 60 Hz (16:9)", 98: "4096x2160 @ 24 Hz (256:135)",
    99: "4096x2160 @ 25 Hz (256:135)", 100: "4096x2160 @ 30 Hz (256:135)",
    101: "4096x2160 @ 50 Hz (256:135)", 102: "4096x2160 @ 60 Hz (256:135)",
}


@dataclass
class EDIDDescriptor:
    name: str
    fields: Dict[str, str] = field(default_factory=dict)
    details: str = ""


@dataclass
class EDIDBaseBlock:
    manufacturer: str = ""
    manufacturer_full: str = ""
    product_code: str = ""
    serial: str = ""
    week: int = 0
    year: int = 0
    version: str = ""
    revision: str = ""
    video_input: str = ""
    max_h_size_cm: int = 0
    max_v_size_cm: int = 0
    gamma: float = 0.0
    features: str = ""
    color_red: Tuple[float, float] = (0.0, 0.0)
    color_green: Tuple[float, float] = (0.0, 0.0)
    color_blue: Tuple[float, float] = (0.0, 0.0)
    color_white: Tuple[float, float] = (0.0, 0.0)
    established_timings: List[str] = field(default_factory=list)
    standard_timings: List[str] = field(default_factory=list)
    detailed_timings: List[EDIDDescriptor] = field(default_factory=list)
    extension_count: int = 0
    checksum: int = 0
    checksum_valid: bool = False


@dataclass
class EDIDCTABlock:
    revision: int = 0
    underscan: bool = False
    basic_audio: bool = False
    ycbcr_444: bool = False
    ycbcr_422: bool = False
    native_detailed_modes: int = 0
    video_data_block: List[str] = field(default_factory=list)
    audio_data_block: List[str] = field(default_factory=list)
    speaker_allocation: List[str] = field(default_factory=list)
    hdmi_vsdb: Dict[str, str] = field(default_factory=dict)
    hdmi_forum_vsdb: Dict[str, str] = field(default_factory=dict)
    hdr_static_metadata: Dict[str, Any] = field(default_factory=dict)
    ycbcr_420_map: List[str] = field(default_factory=list)
    detailed_timings: List[EDIDDescriptor] = field(default_factory=list)
    checksum: int = 0
    checksum_valid: bool = False


@dataclass
class EDIDData:
    path: str
    base: Optional[EDIDBaseBlock] = None
    cta: Optional[EDIDCTABlock] = None
    raw_bytes: bytes = b""


def _decode_manufacturer_id(value: int) -> str:
    letters = []
    for shift in (10, 5, 0):
        code = (value >> shift) & 0x1F
        letters.append(chr(ord('A') + code - 1) if 1 <= code <= 26 else '?')
    return "".join(letters)


def _decode_edid_string(data: bytes) -> str:
    return data.rstrip(b'\x00\x20\x0a').decode('ascii', errors='replace')


def _parse_detailed_timing(block: bytes) -> EDIDDescriptor:
    if len(block) < 18:
        return EDIDDescriptor(name="INVALID")
    pixel_clock = struct.unpack('<H', block[0:2])[0] * 10
    if pixel_clock == 0:
        return EDIDDescriptor(name="SKIP")
    hactive = block[2] | ((block[4] & 0xF0) << 4)
    hblank = block[3] | ((block[4] & 0x0F) << 8)
    vactive = block[5] | ((block[7] & 0xF0) << 4)
    vblank = block[6] | ((block[7] & 0x0F) << 8)
    hfront = block[8] | ((block[11] & 0xC0) << 2)
    hsync = block[9] | ((block[11] & 0x30) << 4)
    vfront = block[10] >> 4 | ((block[11] & 0x0C) << 2)
    vsync = block[10] & 0x0F | ((block[11] & 0x03) << 4)
    htotal = hactive + hblank
    vtotal = vactive + vblank
    refresh = pixel_clock * 1000 / (htotal * vtotal) if htotal and vtotal else 0
    return EDIDDescriptor(
        name=f"{hactive}x{vactive} @ {refresh:.2f} Hz",
        fields={
            "Pixel Clock": f"{pixel_clock / 1000:.3f} MHz",
            "H Active": str(hactive), "H Blank": str(hblank),
            "H Total": str(htotal), "H Front": str(hfront), "H Sync": str(hsync),
            "V Active": str(vactive), "V Blank": str(vblank),
            "V Total": str(vtotal), "V Front": str(vfront), "V Sync": str(vsync),
            "Refresh": f"{refresh:.3f} Hz",
        },
    )


def parse_edid(path: str) -> EDIDData:
    data = EDIDData(path=path)
    with open(path, "rb") as f:
        raw = f.read()
    data.raw_bytes = raw
    if len(raw) < 128:
        return data
    if raw[0:8] != b'\x00\xff\xff\xff\xff\xff\xff\x00':
        return data

    base = EDIDBaseBlock()
    mfg_id = struct.unpack('>H', raw[8:10])[0]
    base.manufacturer = _decode_manufacturer_id(mfg_id)
    base.manufacturer_full = EDID_MANUFACTURER_IDS.get(base.manufacturer, "")
    base.product_code = f"0x{struct.unpack('<H', raw[10:12])[0]:04x}"
    base.serial = str(struct.unpack('<I', raw[12:16])[0])
    base.week = raw[16]
    base.year = 1990 + raw[17]
    base.version = str(raw[18])
    base.revision = str(raw[19])
    base.video_input = "Digital" if (raw[20] & 0x80) else "Analog"
    base.max_h_size_cm = raw[21]
    base.max_v_size_cm = raw[22]
    base.gamma = (raw[23] + 100) / 100.0 if raw[23] != 0xFF else 0.0

    features = raw[24]
    feature_names = []
    if features & 0x80: feature_names.append("Standby")
    if features & 0x40: feature_names.append("Suspend")
    if features & 0x20: feature_names.append("Active Off")
    if features & 0x10: feature_names.append("Digital Separate Sync")
    elif features & 0x08: feature_names.append("Digital Composite Sync")
    if features & 0x04: feature_names.append("Serration")
    if features & 0x02: feature_names.append("Composite Sync on HSync")
    if features & 0x01: feature_names.append("Preferred Timing is Native")
    base.features = ", ".join(feature_names) if feature_names else "None"

    def decode_color(lo, hi):
        x = ((hi << 2) | ((lo >> 6) & 0x03)) / 1024.0
        y = (((hi << 2) | ((lo >> 4) & 0x03)) & 0x3FF) / 1024.0
        return (x, y)
    base.color_red = decode_color(raw[25], raw[27] >> 6)
    base.color_green = decode_color(raw[26], (raw[27] >> 4) & 0x03)
    base.color_blue = decode_color(raw[27] & 0x0F, (raw[27] >> 2) & 0x03)
    base.color_white = decode_color(raw[28], raw[27] & 0x03)

    if raw[35] & 0x80: base.established_timings.append("720x400 @ 70 Hz")
    if raw[35] & 0x40: base.established_timings.append("720x400 @ 88 Hz")
    if raw[35] & 0x20: base.established_timings.append("640x480 @ 60 Hz")
    if raw[35] & 0x10: base.established_timings.append("640x480 @ 67 Hz")
    if raw[35] & 0x08: base.established_timings.append("640x480 @ 72 Hz")
    if raw[35] & 0x04: base.established_timings.append("640x480 @ 75 Hz")
    if raw[35] & 0x02: base.established_timings.append("800x600 @ 56 Hz")
    if raw[35] & 0x01: base.established_timings.append("800x600 @ 60 Hz")
    if raw[36] & 0x80: base.established_timings.append("800x600 @ 72 Hz")
    if raw[36] & 0x40: base.established_timings.append("800x600 @ 75 Hz")
    if raw[36] & 0x20: base.established_timings.append("832x624 @ 75 Hz")
    if raw[36] & 0x10: base.established_timings.append("1024x768 @ 87 Hz (i)")
    if raw[36] & 0x08: base.established_timings.append("1024x768 @ 60 Hz")
    if raw[36] & 0x04: base.established_timings.append("1024x768 @ 70 Hz")
    if raw[36] & 0x02: base.established_timings.append("1024x768 @ 75 Hz")
    if raw[36] & 0x01: base.established_timings.append("1280x1024 @ 75 Hz")
    if raw[37] & 0x80: base.established_timings.append("1152x870 @ 75 Hz (Apple)")

    for i in range(8):
        off = 38 + i * 2
        if off + 1 >= len(raw): break
        b1, b2 = raw[off], raw[off + 1]
        if b1 == 0x01 and b2 == 0x01: continue
        h_pixels = (b1 + 31) * 8
        aspect = (b2 >> 6) & 0x03
        v_pixels_map = {0: h_pixels * 10 // 16, 1: h_pixels * 3 // 4,
                        2: h_pixels * 4 // 5, 3: h_pixels * 9 // 16}
        v_pixels = v_pixels_map[aspect]
        refresh = 60 + (b2 & 0x3F)
        base.standard_timings.append(f"{h_pixels}x{v_pixels} @ {refresh} Hz")

    for i in range(4):
        off = 54 + i * 18
        if off + 18 > 126: break
        block = raw[off:off + 18]
        if block[0] == 0 and block[1] == 0:
            tag = block[3]
            if tag == 0xFC:
                name = _decode_edid_string(block[5:18])
                base.detailed_timings.append(EDIDDescriptor(
                    name=f"Monitor Name: {name}", details=name))
            elif tag == 0xFD:
                v_min, v_max = block[5], block[6]
                h_min, h_max = block[7], block[8]
                max_clock = block[9] * 10
                base.detailed_timings.append(EDIDDescriptor(
                    name="Monitor Range Limits",
                    fields={"V Rate Min": f"{v_min} Hz", "V Rate Max": f"{v_max} Hz",
                            "H Rate Min": f"{h_min} kHz", "H Rate Max": f"{h_max} kHz",
                            "Max Pixel Clock": f"{max_clock} MHz"}))
            elif tag == 0xFE:
                s = _decode_edid_string(block[5:18])
                base.detailed_timings.append(EDIDDescriptor(name=f"ASCII String: {s}"))
            elif tag == 0xFF:
                s = _decode_edid_string(block[5:18])
                base.detailed_timings.append(EDIDDescriptor(name=f"Serial Number: {s}"))
            else:
                base.detailed_timings.append(EDIDDescriptor(
                    name=f"Descriptor tag 0x{tag:02x}"))
        else:
            base.detailed_timings.append(_parse_detailed_timing(block))

    base.extension_count = raw[126]
    base.checksum = raw[127]
    computed = sum(raw[0:127]) & 0xFF
    base.checksum_valid = ((computed + base.checksum) & 0xFF) == 0
    data.base = base

    if base.extension_count >= 1 and len(raw) >= 256:
        ext = raw[128:256]
        if ext[0] == 0x02:
            cta = EDIDCTABlock()
            cta.revision = ext[1]
            dtd_offset = ext[2]
            if cta.revision >= 2:
                flags = ext[3]
                cta.underscan = bool(flags & 0x80)
                cta.basic_audio = bool(flags & 0x40)
                cta.ycbcr_444 = bool(flags & 0x20)
                cta.ycbcr_422 = bool(flags & 0x10)
                cta.native_detailed_modes = flags & 0x0F
            pos = 4
            end = dtd_offset if dtd_offset > 4 else len(ext)
            while pos < end:
                header = ext[pos]
                tag = (header >> 5) & 0x07
                length = header & 0x1F
                block = ext[pos + 1:pos + 1 + length]
                if tag == 2:
                    for vic in block:
                        vic_num = vic & 0x7F
                        name = EDID_VIDEO_FORMATS.get(vic_num, f"VIC {vic_num}")
                        native = " (native)" if vic & 0x80 else ""
                        cta.video_data_block.append(name + native)
                elif tag == 1:
                    i = 0
                    while i + 3 <= len(block):
                        fmt_code = (block[i] >> 3) & 0x1F
                        channels = (block[i] & 0x07) + 1
                        rates = block[i + 1]
                        fmt_names = {
                            1: "Linear PCM", 2: "AC-3", 3: "MPEG-1", 4: "MP3",
                            5: "MPEG2", 6: "AAC LC", 7: "DTS", 8: "ATRAC",
                            9: "One Bit Audio", 10: "Enhanced AC-3 (DD+)",
                            11: "DTS-HD", 12: "MAT (MLP)", 13: "DST", 14: "WMA Pro",
                        }
                        fmt_name = fmt_names.get(fmt_code, f"Format {fmt_code}")
                        rate_names = []
                        if rates & 0x01: rate_names.append("32 kHz")
                        if rates & 0x02: rate_names.append("44.1 kHz")
                        if rates & 0x04: rate_names.append("48 kHz")
                        if rates & 0x08: rate_names.append("88.2 kHz")
                        if rates & 0x10: rate_names.append("96 kHz")
                        if rates & 0x20: rate_names.append("176.4 kHz")
                        if rates & 0x40: rate_names.append("192 kHz")
                        cta.audio_data_block.append(
                            f"{fmt_name}: {channels} ch, {', '.join(rate_names)}")
                        i += 3
                elif tag == 4:
                    spk = block[0] if block else 0
                    spk_names = []
                    if spk & 0x01: spk_names.append("FL/FR")
                    if spk & 0x02: spk_names.append("LFE")
                    if spk & 0x04: spk_names.append("FC")
                    if spk & 0x08: spk_names.append("RL/RR")
                    if spk & 0x10: spk_names.append("RC")
                    if spk & 0x20: spk_names.append("FLC/FRC")
                    if spk & 0x40: spk_names.append("RLC/RRC")
                    cta.speaker_allocation = spk_names
                elif tag == 3:
                    if len(block) >= 3:
                        oui = (block[2] << 16) | (block[1] << 8) | block[0]
                        if oui == 0x000C03:
                            cta.hdmi_vsdb = {
                                "OUI": "HDMI (00-0C-03)",
                                "Source Physical Address":
                                    f"{block[3] >> 4}.{block[3] & 0x0F}."
                                    f"{block[4] >> 4}.{block[4] & 0x0F}"
                                    if len(block) >= 5 else "?",
                                "Raw": block.hex(),
                            }
                            if len(block) >= 7:
                                cta.hdmi_vsdb["Max TMDS Clock"] = f"{block[6] * 5} MHz"
                        elif oui == 0xC45DD8:
                            cta.hdmi_forum_vsdb = {
                                "OUI": "HDMI Forum (C4-5D-D8)",
                                "Version": str(block[3]) if len(block) >= 4 else "?",
                                "Max TMDS Character Rate":
                                    f"{block[4] * 5} MHz" if len(block) >= 5 else "?",
                                "Raw": block.hex(),
                            }
                elif tag == 7:
                    if block:
                        ext_tag = block[0]
                        if ext_tag == 6:
                            hdr = {}
                            if len(block) >= 2:
                                eotf = block[1]
                                hdr["EOTF"] = []
                                if eotf & 0x01: hdr["EOTF"].append("Traditional gamma SDR")
                                if eotf & 0x02: hdr["EOTF"].append("Traditional gamma HDR")
                                if eotf & 0x04: hdr["EOTF"].append("SMPTE ST2084 (HDR10)")
                                if eotf & 0x08: hdr["EOTF"].append("Hybrid Log-Gamma (HLG)")
                            if len(block) >= 3:
                                sm = block[2]
                                hdr["Static Metadata"] = []
                                if sm & 0x01: hdr["Static Metadata"].append("Type 1 (HDR10)")
                                if sm & 0x02: hdr["Static Metadata"].append("Type 2")
                                if sm & 0x04: hdr["Static Metadata"].append("Type 3")
                                if sm & 0x08: hdr["Static Metadata"].append("Type 4")
                            cta.hdr_static_metadata = hdr
                        elif ext_tag == 14:
                            for vic in block[1:]:
                                name = EDID_VIDEO_FORMATS.get(vic, f"VIC {vic}")
                                cta.ycbcr_420_map.append(name)
                pos += 1 + length

            if dtd_offset > 0 and dtd_offset + 18 <= len(ext):
                for i in range((len(ext) - dtd_offset) // 18):
                    off = dtd_offset + i * 18
                    block = ext[off:off + 18]
                    if len(block) < 18: break
                    if block[0] == 0 and block[1] == 0: break
                    cta.detailed_timings.append(_parse_detailed_timing(block))

            cta.checksum = ext[127]
            computed = sum(ext[0:127]) & 0xFF
            cta.checksum_valid = ((computed + cta.checksum) & 0xFF) == 0
            data.cta = cta

    return data


# =============================================================================
# EFSL PARSER (hwprofile / swprofile / devprofile)
# =============================================================================

EFSL_MAGIC = b"EFSL"
EFSL_VERSION = 1

EFSL_KNOWN_TYPES = {
    0x00000000: "Root / Terminator",
    0x00000100: "Generic",
    0x00000105: "String",
    0x00000200: "Numeric",
    0x00000205: "String (v2)",
    0x00000300: "Numeric Setting",
    0x00000500: "Setting",
    0x00000501: "Setting",
    0x00000502: "Numeric Setting",
    0x00000503: "Numeric Setting (v2)",
    0x00000600: "Binary Blob",
    0x00000700: "Array",
}


@dataclass
class EFSLEntry:
    index: int
    type: int
    subtype: int
    value: int
    data_offset: int
    crc32: int
    raw: bytes = b""
    text: Optional[str] = None
    strings: List[str] = field(default_factory=list)
    hex_dump: str = ""
    crc_valid: bool = False
    computed_crc: int = 0

    @property
    def type_name(self) -> str:
        return EFSL_KNOWN_TYPES.get(self.type, f"Unknown (0x{self.type:08x})")


@dataclass
class EFSLData:
    path: str
    magic: bytes = b""
    version: int = 0
    declared_size: int = 0
    reserved: int = 0
    profile_type: str = ""
    entries: List[EFSLEntry] = field(default_factory=list)
    raw: bytes = b""
    parse_errors: List[str] = field(default_factory=list)

    @property
    def actual_size(self) -> int:
        return len(self.raw)


def _format_hex(raw: bytes, max_bytes: int = 512) -> str:
    lines = []
    display = raw[:max_bytes]
    for i in range(0, len(display), 16):
        chunk = display[i:i + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:06x}  {hex_part:<48}  {ascii_part}")
    if len(raw) > max_bytes:
        lines.append(f"... ({len(raw) - max_bytes} more bytes)")
    return "\n".join(lines)


def _try_decode_text(raw: bytes) -> Optional[str]:
    if not raw:
        return None
    stripped = raw.rstrip(b"\x00")
    if not stripped:
        return None
    printable = sum(1 for b in stripped if 32 <= b < 127 or b in (9, 10, 13))
    if printable / len(stripped) > 0.9:
        try:
            return stripped.decode("ascii", errors="replace")
        except Exception:
            return None
    return None


def _extract_strings(raw: bytes, min_len: int = 4) -> List[str]:
    strings = []
    current = []
    for b in raw:
        if 32 <= b < 127:
            current.append(chr(b))
        else:
            if len(current) >= min_len:
                strings.append("".join(current))
            current = []
    if len(current) >= min_len:
        strings.append("".join(current))
    return strings


def parse_efsl(path: str) -> EFSLData:
    with open(path, "rb") as f:
        raw = f.read()

    data = EFSLData(path=path, raw=raw)

    if len(raw) < 32:
        data.parse_errors.append(f"File too small: {len(raw)} bytes (need >= 32)")
        return data

    data.magic = raw[0:4]
    if data.magic != EFSL_MAGIC:
        data.parse_errors.append(
            f"Invalid magic: {data.magic!r} (expected {EFSL_MAGIC!r})")
        return data

    data.version = struct.unpack_from("<I", raw, 4)[0]
    data.declared_size = struct.unpack_from("<I", raw, 8)[0]
    data.reserved = struct.unpack_from("<I", raw, 12)[0]
    data.profile_type = raw[16:32].rstrip(b"\x00").decode("ascii", errors="replace")

    if data.declared_size != data.actual_size:
        data.parse_errors.append(
            f"Note: header declares {data.declared_size:,} bytes; "
            f"file has {data.actual_size:,} bytes "
            f"(difference: {data.declared_size - data.actual_size:+,} bytes, "
            f"reserved space)."
        )

    offset = 0x20
    index = 0
    while offset + 20 <= len(raw):
        etype = struct.unpack_from("<I", raw, offset + 0)[0]
        subtype = struct.unpack_from("<I", raw, offset + 4)[0]
        value = struct.unpack_from("<I", raw, offset + 8)[0]
        data_off = struct.unpack_from("<I", raw, offset + 12)[0]
        crc = struct.unpack_from("<I", raw, offset + 16)[0]

        if etype == 0 and subtype == 0 and value == 0 \
                and data_off == 0 and crc == 0:
            break

        entry = EFSLEntry(
            index=index, type=etype, subtype=subtype, value=value,
            data_offset=data_off, crc32=crc,
        )

        if 0 < data_off < len(raw):
            preview_len = min(256, len(raw) - data_off)
            entry.raw = raw[data_off:data_off + preview_len]
            entry.text = _try_decode_text(entry.raw)
            entry.strings = _extract_strings(entry.raw)
            entry.hex_dump = _format_hex(entry.raw)
            entry.computed_crc = zlib.crc32(entry.raw) & 0xFFFFFFFF
            entry.crc_valid = (entry.computed_crc == crc)

        data.entries.append(entry)
        index += 1
        offset += 20

        if index > 5000:
            data.parse_errors.append("Runaway entry count — aborting at 5000")
            break

    return data


# =============================================================================
# LANGUAGE PROFILE PARSER
# =============================================================================

@dataclass
class LangEntry:
    key_index: int
    key_string: str
    translations: List[str] = field(default_factory=list)
    offsets: List[int] = field(default_factory=list)


@dataclass
class LangProfileData:
    path: str
    header_magic: str = ""
    header_bytes: bytes = b""
    body_offset: int = 0
    total_strings: int = 0
    languages_detected: int = 0
    entries: List[LangEntry] = field(default_factory=list)
    all_strings: List[Tuple[int, str]] = field(default_factory=list)
    raw: bytes = b""
    parse_errors: List[str] = field(default_factory=list)


def _split_null_terminated(raw: bytes, start: int = 0):
    result = []
    offset = start
    while offset < len(raw):
        end = raw.find(b"\x00", offset)
        if end < 0:
            if end - offset > 0:
                result.append((offset, raw[offset:]))
            break
        if end > offset:
            result.append((offset, raw[offset:end]))
        offset = end + 1
    return result


def parse_langprofile(path: str) -> LangProfileData:
    with open(path, "rb") as f:
        raw = f.read()

    data = LangProfileData(path=path, raw=raw)

    header_search_end = min(64, len(raw))
    header_region = raw[:header_search_end]

    if b"langprofile" in header_region:
        idx = header_region.find(b"langprofile")
        data.header_magic = "langprofile"
        data.header_bytes = raw[:idx + 16]
        data.body_offset = idx + 16
    elif raw[:4] == b"EFSL":
        data.header_magic = "EFSL"
        data.header_bytes = raw[:32]
        data.body_offset = 32
    else:
        data.header_magic = "(unknown)"
        data.body_offset = 0
        data.parse_errors.append(
            "No recognizable header found; assuming raw string table from offset 0")

    body = raw[data.body_offset:]
    strings = _split_null_terminated(body)
    data.total_strings = len(strings)

    for off, sb in strings:
        abs_off = data.body_offset + off
        try:
            text = sb.decode("utf-8", errors="replace")
        except Exception:
            continue
        if len(text) < 1:
            continue
        printable = sum(1 for c in text if c.isprintable() or c in " \t")
        if printable / len(text) < 0.8:
            continue
        data.all_strings.append((abs_off, text))

    string_counts = Counter(s for _, s in data.all_strings)
    candidates = [(s, c) for s, c in string_counts.items()
                  if c >= 3 and len(s) >= 4]
    if candidates:
        candidates.sort(key=lambda x: -x[1])
        anchor_str = candidates[0][0]
        anchor_offsets = [off for off, s in data.all_strings if s == anchor_str]
        if len(anchor_offsets) >= 2:
            gaps = [anchor_offsets[i+1] - anchor_offsets[i]
                    for i in range(len(anchor_offsets) - 1)]
            gap_counts = Counter(gaps)
            most_common_gap, freq = gap_counts.most_common(1)[0]
            block_strings = [
                (off, s) for off, s in data.all_strings
                if anchor_offsets[0] <= off < anchor_offsets[0] + most_common_gap
            ]
            data.languages_detected = len(block_strings)
            data.parse_errors.append(
                f"Anchor string: {anchor_str!r} "
                f"(appears {len(anchor_offsets)} times, gap = {most_common_gap} bytes)")
            data.parse_errors.append(
                f"Estimated languages per block: {data.languages_detected}")

    return data


# =============================================================================
# FILE DISCOVERY
# =============================================================================

def discover_files(directory: str) -> Dict[str, List[str]]:
    result = {
        "PTF": [], "EDID": [], "HW Profile": [], "SW Profile": [],
        "Lang Profile": [], "PQ": [], "Audio": [],
        "XML": [], "Text": [], "Other": [],
    }
    path = Path(directory)
    if not path.exists():
        return result
    for f in path.iterdir():
        if not f.is_file():
            continue
        name = f.name.lower()

        if name.endswith(".xml"):
            result["XML"].append(str(f))
        elif name.endswith(".txt") or name.endswith(".log"):
            result["Text"].append(str(f))
        elif name.endswith(".ptf"):
            result["PTF"].append(str(f))
        elif name.startswith("edid") and (name.endswith(".edid") or name.endswith(".vga")):
            result["EDID"].append(str(f))
        elif "hwprofile" in name:
            result["HW Profile"].append(str(f))
        elif "swprofile" in name:
            result["SW Profile"].append(str(f))
        elif "langprofile" in name:
            result["Lang Profile"].append(str(f))
        elif name.endswith(".pcf") or "pqf" in name:
            result["PQ"].append(str(f))
        elif name.endswith(".bin") and any(k in name for k in ("aq", "dap", "dts", "subw")):
            result["Audio"].append(str(f))
        elif name.endswith((".bin", ".dcf")):
            result["Other"].append(str(f))
    return result


# =============================================================================
# GUI APPLICATION
# =============================================================================

class MB230Inspector(tk.Tk):
    def __init__(self, directory: str = "."):
        super().__init__()
        self.title("MB230 Config Inspector")
        self.geometry("1280x820")
        self.minsize(900, 600)
        self.directory = directory
        self.files = discover_files(directory)
        self.current_file: Optional[str] = None
        self.current_data: Any = None
        self.current_type: str = ""
        self._efsl_detail_frame: Optional[ttk.LabelFrame] = None
        self._build_ui()
        self._populate_sidebar()

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=(8, 4))
        toolbar.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(toolbar, text="Directory:").pack(side=tk.LEFT)
        self.dir_var = tk.StringVar(value=self.directory)
        ttk.Entry(toolbar, textvariable=self.dir_var, width=60).pack(
            side=tk.LEFT, padx=(4, 8))
        ttk.Button(toolbar, text="Browse...", command=self._choose_directory).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Reload", command=self._reload).pack(side=tk.LEFT, padx=(4, 0))

        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        sidebar_frame = ttk.Frame(paned, width=260)
        paned.add(sidebar_frame, weight=0)
        ttk.Label(sidebar_frame, text="Files",
                  font=("TkDefaultFont", 11, "bold")).pack(
            side=tk.TOP, anchor=tk.W, padx=8, pady=(8, 4))
        self.tree = ttk.Treeview(sidebar_frame, show="tree", selectmode="browse")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0), pady=4)
        tree_scroll = ttk.Scrollbar(sidebar_frame, orient="vertical", command=self.tree.yview)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=4)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        content_frame = ttk.Frame(paned)
        paned.add(content_frame, weight=1)
        self.content_title = ttk.Label(
            content_frame, text="Select a file from the sidebar",
            font=("TkDefaultFont", 13, "bold"))
        self.content_title.pack(side=tk.TOP, anchor=tk.W, padx=8, pady=(8, 4))
        self.content_subtitle = ttk.Label(content_frame, text="", foreground="#666")
        self.content_subtitle.pack(side=tk.TOP, anchor=tk.W, padx=8, pady=(0, 4))

        content_container = ttk.Frame(content_frame)
        content_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))
        canvas = tk.Canvas(content_container, highlightthickness=0)
        vscroll = ttk.Scrollbar(content_container, orient="vertical", command=canvas.yview)
        self.content_inner = ttk.Frame(canvas)
        self.content_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.content_inner, anchor=tk.NW)
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        self.status = ttk.Label(self, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def _populate_sidebar(self):
        self.tree.delete(*self.tree.get_children())
        icons = {
            "PTF": "[P]", "EDID": "[E]", "HW Profile": "[H]",
            "SW Profile": "[S]", "Lang Profile": "[L]",
            "PQ": "[Q]", "Audio": "[A]",
            "XML": "[X]", "Text": "[T]", "Other": "[.]",
        }
        for category, files in self.files.items():
            if not files:
                continue
            label = f"{icons.get(category, '[?]')}  {category} ({len(files)})"
            parent = self.tree.insert("", "end", text=label, open=True, values=[category])
            for f in sorted(files):
                display = Path(f).name
                self.tree.insert(parent, "end", text=f"    {display}",
                                 values=[category, f])

    def _choose_directory(self):
        d = filedialog.askdirectory(initialdir=self.directory)
        if d:
            self.dir_var.set(d)
            self.directory = d
            self._reload()

    def _reload(self):
        self.directory = self.dir_var.get()
        self.files = discover_files(self.directory)
        self._populate_sidebar()
        self._clear_content()
        self.status.config(text=f"Loaded from {self.directory}")

    def _clear_content(self):
        for widget in self.content_inner.winfo_children():
            widget.destroy()
        self.current_file = None
        self.current_data = None
        self._efsl_detail_frame = None
        self.content_title.config(text="Select a file from the sidebar")
        self.content_subtitle.config(text="")

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        item = self.tree.item(sel[0], "values")
        if len(item) < 2:
            return
        category, path = item[0], item[1]
        if not path:
            return
        self.current_file = path
        self.current_type = category
        self._load_file(path, category)

    def _load_file(self, path: str, category: str):
        self._clear_content()
        self.content_title.config(text=Path(path).name)
        self.content_subtitle.config(text=path)
        try:
            if category == "PTF":
                data = parse_ptf(path)
                self.current_data = data
                self._render_ptf(data)
            elif category == "EDID":
                data = parse_edid(path)
                self.current_data = data
                self._render_edid(data)
            elif category in ("HW Profile", "SW Profile"):
                data = parse_efsl(path)
                self.current_data = data
                self._render_efsl(data)
            elif category == "Lang Profile":
                data = parse_langprofile(path)
                self.current_data = data
                self._render_langprofile(data)
            elif category == "XML":
                self.current_data = None
                self._render_xml_file(path, category)
            elif category == "Text":
                self.current_data = None
                self._render_text_file(path, category)
            elif category in ("PQ", "Audio", "Other"):
                self.current_data = None
                self._render_binary_with_strings(path, category)
            else:
                self._render_binary_with_strings(path, category)
            self.status.config(text=f"Loaded {Path(path).name}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._render_error(f"{type(e).__name__}: {e}")
            self.status.config(text=f"Error: {e}")

    # -------------------------------------------------------------------------
    # RENDER: PTF
    # -------------------------------------------------------------------------

    def _render_ptf(self, data: PTFData):
        summary = ttk.LabelFrame(self.content_inner, text="Summary", padding=8)
        summary.pack(fill=tk.X, pady=(0, 8))
        panel_name = next((e.value for e in data.entries if e.key == "au8Name"), "?")
        revision = next((e.value for e in data.entries if e.key == "Revision"), "?")
        panel_id = next((e.value for e in data.entries if e.key == "u8PanelID"), "?")
        interface = next((e.value for e in data.entries if e.key == "enLvdsFormat"), "0")
        interface_str = "LVDS" if interface == "1" else "V-by-One / other"
        rows = [
            ("Panel Timing Generator", panel_name),
            ("Panel ID", panel_id),
            ("Interface", interface_str),
            ("Revision", revision),
            ("Total entries", str(len(data.entries))),
        ]
        for i, (k, v) in enumerate(rows):
            ttk.Label(summary, text=k, font=("TkDefaultFont", 9, "bold")).grid(
                row=i, column=0, sticky=tk.W, padx=(0, 8), pady=1)
            ttk.Label(summary, text=v).grid(row=i, column=1, sticky=tk.W)

        for mode_name, entries in sorted(data.timing_modes.items()):
            mode_frame = ttk.LabelFrame(
                self.content_inner, text=f"Timing: {mode_name}", padding=8)
            mode_frame.pack(fill=tk.X, pady=(0, 8))
            pll = entries.get(f"{mode_name}.u16PLL")
            ht = entries.get(f"{mode_name}.u16TypHTotal")
            vt = entries.get(f"{mode_name}.u16TypVTotal")
            if pll and ht and vt:
                try:
                    pll_hz = int(pll.value) * 10000
                    ht_v = int(ht.value)
                    vt_v = int(vt.value)
                    refresh = pll_hz / (ht_v * vt_v)
                    ttk.Label(
                        mode_frame,
                        text=f"-> Computed pixel clock: {pll_hz / 1_000_000:.3f} MHz  |  "
                             f"Computed refresh: {refresh:.3f} Hz",
                        foreground="#0055aa",
                        font=("TkDefaultFont", 9, "italic")).pack(anchor=tk.W, pady=(0, 6))
                except (ValueError, ZeroDivisionError):
                    pass

            table = ttk.Treeview(mode_frame,
                                 columns=("key", "value", "desc", "risk"),
                                 show="headings", height=min(len(entries), 12))
            table.heading("key", text="Parameter")
            table.heading("value", text="Value")
            table.heading("desc", text="Description")
            table.heading("risk", text="Risk")
            table.column("key", width=250)
            table.column("value", width=80, anchor=tk.E)
            table.column("desc", width=440)
            table.column("risk", width=70, anchor=tk.CENTER)
            for key, entry in sorted(entries.items()):
                short_key = key.split(".", 1)[1] if "." in key else key
                table.insert("", "end",
                             values=(short_key, entry.value, entry.description,
                                     entry.risk.upper()),
                             tags=(entry.risk,))
            table.tag_configure("safe", background="#e8f5e9")
            table.tag_configure("risky", background="#ffebee")
            table.pack(fill=tk.X, expand=True)

        other_entries = [e for e in data.entries if "." not in e.key]
        if other_entries:
            other_frame = ttk.LabelFrame(
                self.content_inner, text="Panel Configuration", padding=8)
            other_frame.pack(fill=tk.X, pady=(0, 8))
            table = ttk.Treeview(other_frame,
                                 columns=("key", "value", "desc", "risk"),
                                 show="headings", height=min(len(other_entries), 25))
            table.heading("key", text="Parameter")
            table.heading("value", text="Value")
            table.heading("desc", text="Description")
            table.heading("risk", text="Risk")
            table.column("key", width=250)
            table.column("value", width=180, anchor=tk.W)
            table.column("desc", width=440)
            table.column("risk", width=70, anchor=tk.CENTER)
            for entry in sorted(other_entries, key=lambda e: e.key):
                table.insert("", "end",
                             values=(entry.key, entry.value, entry.description,
                                     entry.risk.upper()),
                             tags=(entry.risk,))
            table.tag_configure("safe", background="#e8f5e9")
            table.tag_configure("risky", background="#ffebee")
            table.pack(fill=tk.X, expand=True)

    # -------------------------------------------------------------------------
    # RENDER: EDID
    # -------------------------------------------------------------------------

    def _render_edid(self, data: EDIDData):
        if data.base is None:
            self._render_error("Not a valid EDID file (no header found)")
            return
        base = data.base

        base_frame = ttk.LabelFrame(self.content_inner, text="Base EDID Block", padding=8)
        base_frame.pack(fill=tk.X, pady=(0, 8))
        info_rows = [
            ("Manufacturer", f"{base.manufacturer} ({base.manufacturer_full or 'unknown'})"),
            ("Product Code", base.product_code),
            ("Serial", base.serial),
            ("Manufactured", f"Week {base.week} of {base.year}"),
            ("EDID Version", f"{base.version}.{base.revision}"),
            ("Video Input", base.video_input),
            ("Max Image Size", f"{base.max_h_size_cm} cm x {base.max_v_size_cm} cm"),
            ("Gamma", f"{base.gamma:.2f}" if base.gamma else "Not defined"),
            ("Features", base.features),
            ("Checksum", f"0x{base.checksum:02x} "
                         f"({'valid' if base.checksum_valid else 'INVALID'})"),
        ]
        for i, (k, v) in enumerate(info_rows):
            ttk.Label(base_frame, text=k,
                      font=("TkDefaultFont", 9, "bold")).grid(
                row=i, column=0, sticky=tk.W, padx=(0, 8), pady=1)
            color = "#cc0000" if k == "Checksum" and not base.checksum_valid else "#000000"
            ttk.Label(base_frame, text=v, foreground=color).grid(
                row=i, column=1, sticky=tk.W)

        color_frame = ttk.LabelFrame(self.content_inner,
                                     text="Color Characteristics", padding=8)
        color_frame.pack(fill=tk.X, pady=(0, 8))
        color_rows = [
            ("Red", f"x={base.color_red[0]:.4f}, y={base.color_red[1]:.4f}"),
            ("Green", f"x={base.color_green[0]:.4f}, y={base.color_green[1]:.4f}"),
            ("Blue", f"x={base.color_blue[0]:.4f}, y={base.color_blue[1]:.4f}"),
            ("White", f"x={base.color_white[0]:.4f}, y={base.color_white[1]:.4f}"),
        ]
        for i, (k, v) in enumerate(color_rows):
            ttk.Label(color_frame, text=k, font=("TkDefaultFont", 9, "bold")).grid(
                row=i, column=0, sticky=tk.W, padx=(0, 8), pady=1)
            ttk.Label(color_frame, text=v).grid(row=i, column=1, sticky=tk.W)

        if base.established_timings:
            self._render_list_section("Established Timings", base.established_timings)
        if base.standard_timings:
            self._render_list_section("Standard Timings", base.standard_timings)
        if base.detailed_timings:
            self._render_detailed_descriptors("Detailed Timing Descriptors",
                                              base.detailed_timings)

        if data.cta is not None:
            cta = data.cta
            cta_frame = ttk.LabelFrame(
                self.content_inner,
                text=f"CTA-861 Extension Block (rev {cta.revision})", padding=8)
            cta_frame.pack(fill=tk.X, pady=(0, 8))
            flags = [
                ("Underscan", "Yes" if cta.underscan else "No"),
                ("Basic Audio", "Yes" if cta.basic_audio else "No"),
                ("YCbCr 4:4:4", "Yes" if cta.ycbcr_444 else "No"),
                ("YCbCr 4:2:2", "Yes" if cta.ycbcr_422 else "No"),
                ("Native DTDs", str(cta.native_detailed_modes)),
                ("Checksum", f"0x{cta.checksum:02x} "
                             f"({'valid' if cta.checksum_valid else 'INVALID'})"),
            ]
            for i, (k, v) in enumerate(flags):
                ttk.Label(cta_frame, text=k,
                          font=("TkDefaultFont", 9, "bold")).grid(
                    row=i, column=0, sticky=tk.W, padx=(0, 8), pady=1)
                color = "#cc0000" if k == "Checksum" and not cta.checksum_valid else "#000000"
                ttk.Label(cta_frame, text=v, foreground=color).grid(
                    row=i, column=1, sticky=tk.W)

            if cta.video_data_block:
                self._render_list_section("Video Data Block (VICs)", cta.video_data_block)
            if cta.audio_data_block:
                self._render_list_section("Audio Data Block", cta.audio_data_block)
            if cta.speaker_allocation:
                self._render_list_section("Speaker Allocation", cta.speaker_allocation)
            if cta.ycbcr_420_map:
                self._render_list_section("YCbCr 4:2:0 Capability Map", cta.ycbcr_420_map)
            if cta.hdmi_vsdb:
                self._render_kv_section("HDMI Vendor-Specific Data Block", cta.hdmi_vsdb)
            if cta.hdmi_forum_vsdb:
                self._render_kv_section("HDMI Forum Vendor-Specific Data Block",
                                        cta.hdmi_forum_vsdb)
            if cta.hdr_static_metadata:
                flat = {}
                for k, v in cta.hdr_static_metadata.items():
                    flat[k] = ", ".join(v) if isinstance(v, list) and v else str(v)
                self._render_kv_section("HDR Static Metadata", flat)
            if cta.detailed_timings:
                self._render_detailed_descriptors("CTA Detailed Timing Descriptors",
                                                  cta.detailed_timings)

        self._render_hex_section("Raw Hex", data.raw_bytes)

    def _render_list_section(self, title: str, items: List[str]):
        frame = ttk.LabelFrame(self.content_inner, text=title, padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))
        for item in items:
            ttk.Label(frame, text=f"- {item}").pack(anchor=tk.W)

    def _render_kv_section(self, title: str, data: Dict[str, str]):
        frame = ttk.LabelFrame(self.content_inner, text=title, padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))
        for k, v in data.items():
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, anchor=tk.W)
            ttk.Label(row, text=k, font=("TkDefaultFont", 9, "bold"),
                      width=28, anchor=tk.W).pack(side=tk.LEFT)
            ttk.Label(row, text=str(v), wraplength=600,
                      justify=tk.LEFT).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _render_detailed_descriptors(self, title: str,
                                     descriptors: List[EDIDDescriptor]):
        frame = ttk.LabelFrame(self.content_inner, text=title, padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))
        for d in descriptors:
            if d.name == "SKIP":
                continue
            sub = ttk.LabelFrame(frame, text=d.name, padding=6)
            sub.pack(fill=tk.X, pady=(0, 4))
            if d.fields:
                for k, v in d.fields.items():
                    row = ttk.Frame(sub)
                    row.pack(fill=tk.X)
                    ttk.Label(row, text=k, font=("TkDefaultFont", 9, "bold"),
                              width=18, anchor=tk.W).pack(side=tk.LEFT)
                    ttk.Label(row, text=v).pack(side=tk.LEFT)
            elif d.details:
                ttk.Label(sub, text=d.details).pack(anchor=tk.W)

    # -------------------------------------------------------------------------
    # RENDER: EFSL (hwprofile / swprofile)
    # -------------------------------------------------------------------------

    def _render_efsl(self, data: EFSLData):
        header_frame = ttk.LabelFrame(self.content_inner, text="EFSL Header", padding=8)
        header_frame.pack(fill=tk.X, pady=(0, 8))
        size_diff = data.declared_size - data.actual_size
        header_rows = [
            ("Magic", data.magic.decode("ascii", errors="replace")),
            ("Version", str(data.version)),
            ("Declared Size", f"{data.declared_size:,} bytes (reserved allocation)"),
            ("Actual Size", f"{data.actual_size:,} bytes"),
            ("Reserved Space",
             f"{size_diff:+,} bytes ({100 * size_diff / data.declared_size:.1f}%)"
             if size_diff else "0 bytes"),
            ("Profile Type", data.profile_type),
            ("Entry Count", str(len(data.entries))),
        ]
        for i, (k, v) in enumerate(header_rows):
            ttk.Label(header_frame, text=k,
                      font=("TkDefaultFont", 9, "bold")).grid(
                row=i, column=0, sticky=tk.W, padx=(0, 8), pady=1)
            ttk.Label(header_frame, text=v).grid(row=i, column=1, sticky=tk.W)

        if data.parse_errors:
            info_frame = ttk.LabelFrame(self.content_inner, text="Notes", padding=8)
            info_frame.pack(fill=tk.X, pady=(0, 8))
            for err in data.parse_errors:
                ttk.Label(info_frame, text=f"- {err}",
                          foreground="#666666", wraplength=900,
                          justify=tk.LEFT).pack(anchor=tk.W)

        self._render_extracted_strings(data.raw, min_len=4,
                                       title="Extracted Strings")

        entries_frame = ttk.LabelFrame(self.content_inner, text="Entry Table", padding=8)
        entries_frame.pack(fill=tk.X, pady=(0, 8))

        table = ttk.Treeview(
            entries_frame,
            columns=("idx", "type", "subtype", "value", "offset", "crc", "preview"),
            show="headings",
            height=min(len(data.entries), 25))
        table.heading("idx", text="#")
        table.heading("type", text="Type")
        table.heading("subtype", text="Subtype")
        table.heading("value", text="Value")
        table.heading("offset", text="Data Offset")
        table.heading("crc", text="CRC32")
        table.heading("preview", text="Preview")

        table.column("idx", width=40, anchor=tk.CENTER)
        table.column("type", width=180)
        table.column("subtype", width=80, anchor=tk.E)
        table.column("value", width=100, anchor=tk.E)
        table.column("offset", width=100, anchor=tk.E)
        table.column("crc", width=100, anchor=tk.W)
        table.column("preview", width=280)

        for entry in data.entries:
            preview = ""
            if entry.text:
                preview = entry.text[:60].replace("\n", " ")
            elif entry.strings:
                preview = entry.strings[0][:60]
            elif entry.raw:
                preview = f"<binary {len(entry.raw)} bytes>"
            else:
                preview = "<data not in dump>"

            table.insert("", "end", iid=str(entry.index),
                         values=(
                             entry.index,
                             entry.type_name,
                             f"0x{entry.subtype:08x}",
                             f"0x{entry.value:08x}",
                             f"0x{entry.data_offset:04x}",
                             f"0x{entry.crc32:08x}",
                             preview,
                         ))

        table.pack(fill=tk.X, expand=True)

        self._efsl_detail_frame = ttk.LabelFrame(
            self.content_inner, text="Entry Detail", padding=8)
        self._efsl_detail_frame.pack(fill=tk.X, pady=(0, 8))

        def on_select(_event):
            sel = table.selection()
            if not sel:
                return
            idx = int(sel[0])
            entry = next((e for e in data.entries if e.index == idx), None)
            if entry:
                self._render_efsl_entry_detail(entry)

        table.bind("<<TreeviewSelect>>", on_select)

        if data.entries:
            table.selection_set(str(data.entries[0].index))
            self._render_efsl_entry_detail(data.entries[0])

        self._render_hex_section("Raw File Hex (first 2 KB)", data.raw[:2048])
        self._render_hex_section("Raw File Hex (last 4 KB)",
                                 data.raw[-4096:] if len(data.raw) > 4096 else data.raw)

    def _render_efsl_entry_detail(self, entry: EFSLEntry):
        for widget in self._efsl_detail_frame.winfo_children():
            widget.destroy()
        info = ttk.Frame(self._efsl_detail_frame)
        info.pack(fill=tk.X, anchor=tk.W)
        rows = [
            ("Index", str(entry.index)),
            ("Type", f"{entry.type_name} (0x{entry.type:08x})"),
            ("Subtype", f"0x{entry.subtype:08x}"),
            ("Value", f"0x{entry.value:08x} ({entry.value})"),
            ("Data Offset", f"0x{entry.data_offset:06x} ({entry.data_offset})"),
            ("Stored CRC32", f"0x{entry.crc32:08x}"),
            ("Preview Bytes", str(len(entry.raw))),
        ]
        for i, (k, v) in enumerate(rows):
            ttk.Label(info, text=k, font=("TkDefaultFont", 9, "bold")).grid(
                row=i, column=0, sticky=tk.W, padx=(0, 8), pady=1)
            ttk.Label(info, text=v).grid(row=i, column=1, sticky=tk.W)
        if entry.text:
            text_frame = ttk.LabelFrame(self._efsl_detail_frame,
                                        text="Decoded Text", padding=6)
            text_frame.pack(fill=tk.X, pady=(6, 0))
            ttk.Label(text_frame, text=entry.text, wraplength=800,
                      justify=tk.LEFT).pack(anchor=tk.W)
        if entry.strings and len(entry.strings) > 1:
            strings_frame = ttk.LabelFrame(self._efsl_detail_frame,
                                           text="Embedded Strings", padding=6)
            strings_frame.pack(fill=tk.X, pady=(6, 0))
            for s in entry.strings:
                ttk.Label(strings_frame, text=f"- {s}").pack(anchor=tk.W)
        if entry.raw:
            hex_frame = ttk.LabelFrame(self._efsl_detail_frame,
                                       text="Entry Data Hex Dump", padding=6)
            hex_frame.pack(fill=tk.X, pady=(6, 0))
            text = tk.Text(hex_frame, height=min(20, max(4, len(entry.raw) // 16 + 1)),
                           width=80, font=("Courier", 9), wrap=tk.NONE)
            text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            text.insert("1.0", entry.hex_dump)
            text.config(state=tk.DISABLED)
            sb = ttk.Scrollbar(hex_frame, orient="vertical", command=text.yview)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            text.configure(yscrollcommand=sb.set)

    # -------------------------------------------------------------------------
    # RENDER: LANGUAGE PROFILE
    # -------------------------------------------------------------------------

    def _render_langprofile(self, data: LangProfileData):
        header_frame = ttk.LabelFrame(self.content_inner,
                                      text="Language Profile Header",
                                      padding=8)
        header_frame.pack(fill=tk.X, pady=(0, 8))
        header_rows = [
            ("Header Magic", data.header_magic),
            ("Header Size", f"{data.body_offset} bytes"),
            ("Body Offset", f"0x{data.body_offset:06x}"),
            ("File Size", f"{len(data.raw):,} bytes"),
            ("Total Strings", f"{data.total_strings:,}"),
            ("Readable Strings", f"{len(data.all_strings):,}"),
            ("Languages / Block",
             str(data.languages_detected) if data.languages_detected else "unknown"),
        ]
        for i, (k, v) in enumerate(header_rows):
            ttk.Label(header_frame, text=k,
                      font=("TkDefaultFont", 9, "bold")).grid(
                row=i, column=0, sticky=tk.W, padx=(0, 8), pady=1)
            ttk.Label(header_frame, text=v).grid(row=i, column=1, sticky=tk.W)

        if data.parse_errors:
            info_frame = ttk.LabelFrame(self.content_inner, text="Notes", padding=8)
            info_frame.pack(fill=tk.X, pady=(0, 8))
            for err in data.parse_errors:
                ttk.Label(info_frame, text=f"- {err}",
                          foreground="#666666", wraplength=900,
                          justify=tk.LEFT).pack(anchor=tk.W)

        strings_frame = ttk.LabelFrame(
            self.content_inner,
            text=f"String Table ({len(data.all_strings):,} entries)",
            padding=8)
        strings_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        filter_frame = ttk.Frame(strings_frame)
        filter_frame.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT)
        filter_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=filter_var, width=40).pack(
            side=tk.LEFT, padx=(4, 8))
        count_label = ttk.Label(filter_frame, text="")
        count_label.pack(side=tk.LEFT)

        tree_frame = ttk.Frame(strings_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        tree = ttk.Treeview(tree_frame,
                            columns=("offset", "string"),
                            show="headings",
                            height=30)
        tree.heading("offset", text="Offset")
        tree.heading("string", text="String (UTF-8)")
        tree.column("offset", width=100, anchor=tk.E)
        tree.column("string", width=900)

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        def populate(filter_text=""):
            for item in tree.get_children():
                tree.delete(item)
            count = 0
            for off, s in data.all_strings:
                if filter_text and filter_text.lower() not in s.lower():
                    continue
                tree.insert("", "end", values=(f"0x{off:06x}", s))
                count += 1
                if count >= 5000:
                    break
            count_label.config(text=f"{count} shown")

        populate()
        filter_var.trace_add("write", lambda *_: populate(filter_var.get()))

        self._render_hex_section("Raw Hex (first 2 KB)", data.raw[:2048])

    # -------------------------------------------------------------------------
    # RENDER: XML
    # -------------------------------------------------------------------------

    def _render_xml_file(self, path: str, category: str):
        """Render an XML file with Tree and Code views."""
        import xml.etree.ElementTree as ET

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read()
        except Exception as e:
            self._render_error(f"Failed to read file: {e}")
            return

        parse_error = None
        tree_root = None
        try:
            tree_root = ET.fromstring(raw_text)
        except ET.ParseError as e:
            parse_error = str(e)

        summary = ttk.LabelFrame(self.content_inner, text="XML Summary", padding=8)
        summary.pack(fill=tk.X, pady=(0, 8))

        size = len(raw_text.encode("utf-8"))
        line_count = raw_text.count("\n") + 1
        rows = [
            ("Category", category),
            ("Size", f"{size:,} bytes"),
            ("Lines", f"{line_count:,}"),
            ("Parsed", "OK" if tree_root is not None else "FAILED"),
        ]
        if tree_root is not None:
            def count_nodes(el):
                return 1 + sum(count_nodes(child) for child in el)
            rows.append(("Total Elements", f"{count_nodes(tree_root):,}"))
            rows.append(("Root Tag", tree_root.tag))

        for i, (k, v) in enumerate(rows):
            ttk.Label(summary, text=k,
                      font=("TkDefaultFont", 9, "bold")).grid(
                row=i, column=0, sticky=tk.W, padx=(0, 8), pady=1)
            color = "#cc0000" if k == "Parsed" and tree_root is None else "#000000"
            ttk.Label(summary, text=v, foreground=color).grid(
                row=i, column=1, sticky=tk.W)

        if parse_error:
            err_frame = ttk.LabelFrame(self.content_inner,
                                       text="Parse Error", padding=8)
            err_frame.pack(fill=tk.X, pady=(0, 8))
            ttk.Label(err_frame, text=parse_error,
                      foreground="#cc0000", wraplength=900,
                      justify=tk.LEFT).pack(anchor=tk.W)

        notebook = ttk.Notebook(self.content_inner)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        tree_tab = ttk.Frame(notebook, padding=8)
        notebook.add(tree_tab, text="Tree View")

        if tree_root is not None:
            self._build_xml_tree_view(tree_tab, tree_root)
        else:
            ttk.Label(tree_tab,
                      text="Cannot show tree view: XML failed to parse.",
                      foreground="#888").pack(anchor=tk.W)

        code_tab = ttk.Frame(notebook, padding=8)
        notebook.add(code_tab, text="Code View")
        pretty = self._pretty_print_xml(raw_text, tree_root)
        self._build_text_view(code_tab, pretty)

        raw_tab = ttk.Frame(notebook, padding=8)
        notebook.add(raw_tab, text="Raw")
        self._build_text_view(raw_tab, raw_text)

    def _build_xml_tree_view(self, parent, root):
        """Build a collapsible tree view of the XML structure."""
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)

        tree = ttk.Treeview(container,
                            columns=("value",),
                            show="tree headings",
                            selectmode="browse")
        tree.heading("#0", text="Element")
        tree.heading("value", text="Text / Attributes")
        tree.column("#0", width=300, anchor=tk.W)
        tree.column("value", width=500, anchor=tk.W)

        def add_node(parent_id, element):
            label = element.tag
            text = (element.text or "").strip()
            if len(text) > 100:
                text = text[:97] + "..."
            attrs = element.attrib
            if attrs:
                attr_str = " ".join(f'{k}="{v}"' for k, v in attrs.items())
                if len(attr_str) > 200:
                    attr_str = attr_str[:197] + "..."
                value_str = f"[{attr_str}]"
                if text:
                    value_str += f"  {text}"
            else:
                value_str = text
            node_id = tree.insert(parent_id, "end",
                                  text=label, values=(value_str,),
                                  open=(parent_id == ""))
            for child in element:
                add_node(node_id, child)
            return node_id

        add_node("", root)

        yscroll = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=yscroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(4, 0), before=container)

        def expand_all():
            def rec(item):
                tree.item(item, open=True)
                for child in tree.get_children(item):
                    rec(child)
            for item in tree.get_children(""):
                rec(item)

        def collapse_all():
            def rec(item):
                tree.item(item, open=False)
                for child in tree.get_children(item):
                    rec(child)
            for item in tree.get_children(""):
                rec(item)

        ttk.Button(btn_frame, text="Expand All",
                   command=expand_all).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Collapse All",
                   command=collapse_all).pack(side=tk.LEFT)

    def _pretty_print_xml(self, raw_text: str, tree_root) -> str:
        import xml.etree.ElementTree as ET
        if tree_root is not None:
            try:
                if hasattr(ET, "indent"):
                    tree = ET.ElementTree(tree_root)
                    ET.indent(tree, space="  ")
                    return ET.tostring(tree_root, encoding="unicode")
                else:
                    return ET.tostring(tree_root, encoding="unicode")
            except Exception:
                pass
        return raw_text

    def _build_text_view(self, parent, content: str):
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)

        text = tk.Text(container, height=30, width=120,
                       font=("Courier", 9), wrap=tk.NONE)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text.insert("1.0", content)
        text.config(state=tk.DISABLED)

        yscroll = ttk.Scrollbar(container, orient="vertical", command=text.yview)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll = ttk.Scrollbar(container, orient="horizontal", command=text.xview)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

    # -------------------------------------------------------------------------
    # RENDER: TEXT
    # -------------------------------------------------------------------------

    def _render_text_file(self, path: str, category: str):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            self._render_error(f"Failed to read file: {e}")
            return

        summary = ttk.LabelFrame(self.content_inner, text="File Summary", padding=8)
        summary.pack(fill=tk.X, pady=(0, 8))
        lines = content.splitlines()
        size = len(content.encode("utf-8"))
        rows = [
            ("Category", category),
            ("Size", f"{size:,} bytes"),
            ("Lines", f"{len(lines):,}"),
            ("Encoding", "UTF-8"),
        ]
        for i, (k, v) in enumerate(rows):
            ttk.Label(summary, text=k,
                      font=("TkDefaultFont", 9, "bold")).grid(
                row=i, column=0, sticky=tk.W, padx=(0, 8), pady=1)
            ttk.Label(summary, text=v).grid(row=i, column=1, sticky=tk.W)

        content_frame = ttk.LabelFrame(self.content_inner, text="Content", padding=8)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        text = tk.Text(content_frame, height=30, width=120,
                       font=("Courier", 9), wrap=tk.NONE)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text.insert("1.0", content)
        text.config(state=tk.DISABLED)

        yscroll = ttk.Scrollbar(content_frame, orient="vertical", command=text.yview)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll = ttk.Scrollbar(content_frame, orient="horizontal", command=text.xview)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

    # -------------------------------------------------------------------------
    # RENDER: BINARY (PQ / Audio / Other)
    # -------------------------------------------------------------------------

    def _render_extracted_strings(self, raw: bytes,
                                  min_len: int = 4,
                                  title: str = "Extracted Strings"):
        strings = []
        current = []
        start = 0
        for i, b in enumerate(raw):
            if 32 <= b < 127:
                if not current:
                    start = i
                current.append(chr(b))
            else:
                if len(current) >= min_len:
                    strings.append((start, "".join(current)))
                current = []
        if len(current) >= min_len:
            strings.append((start, "".join(current)))

        if not strings:
            frame = ttk.LabelFrame(self.content_inner, text=title, padding=8)
            frame.pack(fill=tk.X, pady=(0, 8))
            ttk.Label(frame,
                      text=f"(no printable strings of length >= {min_len} found)",
                      foreground="#888").pack(anchor=tk.W)
            return

        frame = ttk.LabelFrame(
            self.content_inner,
            text=f"{title} ({len(strings):,} found, length >= {min_len})",
            padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))

        listbox_frame = ttk.Frame(frame)
        listbox_frame.pack(fill=tk.X, expand=True)

        text = tk.Text(listbox_frame, height=min(len(strings), 20),
                       width=100, font=("Courier", 9), wrap=tk.NONE)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text.config(state=tk.NORMAL)
        for off, s in strings:
            safe = s.replace("\t", "\\t")
            text.insert(tk.END, f"0x{off:06x} ({off:>7d})  {safe}\n")
        text.config(state=tk.DISABLED)

        sb = ttk.Scrollbar(listbox_frame, orient="vertical", command=text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        text.configure(yscrollcommand=sb.set)

    def _render_binary_with_strings(self, path: str, category: str):
        with open(path, "rb") as f:
            raw = f.read()

        summary = ttk.LabelFrame(self.content_inner, text="File Summary", padding=8)
        summary.pack(fill=tk.X, pady=(0, 8))

        size = len(raw)
        md5 = hashlib.md5(raw).hexdigest()
        sha1 = hashlib.sha1(raw).hexdigest()
        sig = self._detect_signature(raw)

        rows = [
            ("Category", category),
            ("Size", f"{size:,} bytes (0x{size:x})"),
            ("MD5", md5),
            ("SHA-1", sha1),
            ("Detected Format", sig if sig else "(unknown / raw binary)"),
        ]
        for i, (k, v) in enumerate(rows):
            ttk.Label(summary, text=k,
                      font=("TkDefaultFont", 9, "bold")).grid(
                row=i, column=0, sticky=tk.W, padx=(0, 8), pady=1)
            lbl = ttk.Label(summary, text=v)
            if k in ("MD5", "SHA-1"):
                lbl.configure(font=("Courier", 9))
            lbl.grid(row=i, column=1, sticky=tk.W)

        self._render_extracted_strings(raw, min_len=4,
                                       title="Extracted Strings (length >= 4)")
        self._render_extracted_strings(raw, min_len=2,
                                       title="Short Strings (length >= 2)")

        self._render_hex_section("Raw Hex (first 2 KB)", raw[:2048])
        if len(raw) > 4096:
            self._render_hex_section("Raw Hex (last 2 KB)", raw[-2048:])

    def _detect_signature(self, raw: bytes) -> str:
        if len(raw) < 4:
            return ""
        sigs = [
            (b"EFSL", "Novatek EFSL profile"),
            (b"\x89PNG", "PNG image"),
            (b"\xff\xd8\xff", "JPEG image"),
            (b"GIF8", "GIF image"),
            (b"BM", "BMP image"),
            (b"PACK", "Novatek PACK container"),
            (b"UBI#", "UBI filesystem"),
            (b"hsqs", "SquashFS (little-endian)"),
            (b"sqsh", "SquashFS (big-endian)"),
            (b"\x1f\x8b", "gzip compressed data"),
            (b"BZh", "bzip2 compressed data"),
            (b"\xfd7zXZ", "XZ compressed data"),
            (b"PK\x03\x04", "ZIP archive"),
            (b"7z\xbc\xaf\x27\x1c", "7z archive"),
            (b"RIFF", "RIFF container (WAV/AVI)"),
            (b"OggS", "Ogg stream"),
            (b"fLaC", "FLAC audio"),
            (b"ID3", "MP3 with ID3 tag"),
            (b"\xff\xfb", "MP3 audio"),
            (b"Rar!", "RAR archive"),
            (b"SQLite format 3", "SQLite database"),
            (b"\x7fELF", "ELF executable/library"),
        ]
        for sig, name in sigs:
            if raw.startswith(sig):
                return name
        if b"NVTPACK_FW" in raw[:256]:
            return "Novatek firmware pack"
        if b"BCL1" in raw[:256]:
            return "Novatek BCL1 container"
        return ""

    # -------------------------------------------------------------------------
    # RENDER: HEX / PLACEHOLDER / ERROR
    # -------------------------------------------------------------------------

    def _render_hex_section(self, title: str, raw: bytes):
        frame = ttk.LabelFrame(self.content_inner, text=title, padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))
        lines = []
        for i in range(0, len(raw), 16):
            chunk = raw[i:i + 16]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{i:06x}  {hex_part:<48}  {ascii_part}")
        text = tk.Text(frame, height=min(len(lines), 20), width=80,
                       font=("Courier", 9), wrap=tk.NONE)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text.insert("1.0", "\n".join(lines))
        text.config(state=tk.DISABLED)
        sb = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        text.configure(yscrollcommand=sb.set)

    def _render_placeholder(self, category: str, path: str):
        frame = ttk.LabelFrame(self.content_inner, text=category, padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(frame, text=f"Viewer for '{category}' is not yet implemented.",
                  foreground="#888").pack(anchor=tk.W)
        ttk.Label(frame, text=f"File: {path}", foreground="#888").pack(anchor=tk.W)
        try:
            with open(path, "rb") as f:
                raw = f.read(4096)
            self._render_hex_section("Raw Hex (first 4 KB)", raw)
        except Exception:
            pass

    def _render_error(self, message: str):
        frame = ttk.LabelFrame(self.content_inner, text="Error", padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(frame, text=message, foreground="#cc0000",
                  wraplength=800, justify=tk.LEFT).pack(anchor=tk.W)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="MB230 Config Inspector - PTF, EDID, EFSL, language, XML, text, binary")
    parser.add_argument("--dir", "-d", default=".",
                        help="Directory containing the MB230 dump files")
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        print(f"Error: directory not found: {args.dir}", file=sys.stderr)
        sys.exit(1)

    app = MB230Inspector(directory=args.dir)
    app.mainloop()


if __name__ == "__main__":
    main()