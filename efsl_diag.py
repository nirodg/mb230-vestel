#!/usr/bin/env python3
"""EFSL Entry Sniper — finds the entry structure by analyzing 0x0105 occurrences."""

import sys
import struct
from pathlib import Path
from collections import Counter

path = sys.argv[1] if len(sys.argv) > 1 else "mb230_hwprofile.bin"
raw = Path(path).read_bytes()
print(f"File: {path}, size: {len(raw):,}")
print()

# Find all occurrences of 0x0105 as a 2-byte LE value
needle = struct.pack("<H", 0x0105)
offsets = []
start = 0
while True:
    idx = raw.find(needle, start)
    if idx < 0:
        break
    offsets.append(idx)
    start = idx + 1

print(f"Found {len(offsets)} occurrences of 0x0105")
print()

# Compute spacing between consecutive occurrences
gaps = [offsets[i+1] - offsets[i] for i in range(len(offsets)-1)]
gap_counts = Counter(gaps)
print("Most common gaps between 0x0105 occurrences:")
for gap, count in gap_counts.most_common(10):
    print(f"  {gap} bytes: {count} times")
print()

# Show first 10 occurrences with 24 bytes of context
print("First 10 occurrences of 0x0105 with context:")
for i, off in enumerate(offsets[:10]):
    start = max(0, off - 4)
    end = min(len(raw), off + 20)
    context = raw[start:end]
    # Highlight the 0x0105 position
    hex_str = " ".join(f"{b:02x}" for b in context)
    print(f"  [{i}] @0x{off:04x}: {hex_str}")
print()

# Align to a hypothesis: entries are 20 bytes and 0x0105 is at offset +0
# Filter offsets that satisfy (off - 0x20) % 20 == 0
print("0x0105 occurrences aligned to 20-byte entry boundaries (offset +0):")
aligned = [o for o in offsets if (o - 0x20) % 20 == 0]
print(f"  Count: {len(aligned)}")
print(f"  First 5 offsets: {[hex(o) for o in aligned[:5]]}")
print()

print("0x0105 occurrences aligned to 20-byte entry boundaries (offset +2):")
aligned2 = [o for o in offsets if (o - 0x22) % 20 == 0]
print(f"  Count: {len(aligned2)}")
print()

print("0x0105 occurrences aligned to 24-byte entry boundaries (offset +0):")
aligned24 = [o for o in offsets if (o - 0x20) % 24 == 0]
print(f"  Count: {len(aligned24)}")
print()

print("0x0105 occurrences aligned to 16-byte entry boundaries (offset +0):")
aligned16 = [o for o in offsets if (o - 0x20) % 16 == 0]
print(f"  Count: {len(aligned16)}")
print()

# The count with the highest alignment is likely the correct entry size