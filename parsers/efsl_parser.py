def _parse_header(raw: bytes, path: str) -> EFSLData:
    data = EFSLData(path=path, raw=raw)

    if len(raw) < 32:
        data.parse_errors.append(f"File too small: {len(raw)} bytes")
        return data

    data.magic = raw[0:4]
    if data.magic != EFSL_MAGIC:
        data.parse_errors.append(f"Invalid magic: {data.magic!r}")
        return data

    data.version = struct.unpack_from("<I", raw, 4)[0]
    data.declared_size = struct.unpack_from("<I", raw, 8)[0]
    data.reserved = struct.unpack_from("<I", raw, 12)[0]
    data.profile_type = raw[16:32].rstrip(b"\x00").decode("ascii", errors="replace")

    # NOTE: declared_size often exceeds actual file size on consumer TVs.
    # This is not an error — the header reserves space for factory entries.
    # We simply note the difference, but don't flag it as a parse failure.
    return data


@dataclass
class EFSLEntry:
    index: int
    type: int           # +0x00
    subtype: int        # +0x04
    value: int          # +0x08
    data_offset: int    # +0x0C
    crc32: int          # +0x10
    raw: bytes = b""
    text: Optional[str] = None

    @property
    def type_name(self) -> str:
        known = {
            0x00000100: "Generic",
            0x00000105: "String",
            0x00000205: "String (v2)",
            0x00000300: "Numeric",
            0x00000502: "Setting",
            0x00000600: "Binary Blob",
        }
        return known.get(self.type, f"Unknown (0x{self.type:08x})")


def parse_efsl(path: str) -> EFSLData:
    with open(path, "rb") as f:
        raw = f.read()

    data = _parse_header(raw, path)
    if data.magic != EFSL_MAGIC:
        return data

    # Parse 20-byte entries starting at 0x20
    offset = 0x20
    index = 0
    while offset + 20 <= len(raw):
        etype = struct.unpack_from("<I", raw, offset + 0)[0]
        subtype = struct.unpack_from("<I", raw, offset + 4)[0]
        value = struct.unpack_from("<I", raw, offset + 8)[0]
        data_off = struct.unpack_from("<I", raw, offset + 12)[0]
        crc = struct.unpack_from("<I", raw, offset + 16)[0]

        # Terminator: all-zero entry
        if etype == 0 and subtype == 0 and value == 0 \
                and data_off == 0 and crc == 0:
            break

        entry = EFSLEntry(
            index=index,
            type=etype,
            subtype=subtype,
            value=value,
            data_offset=data_off,
            crc32=crc,
        )

        # Try to read a bit of data for preview (bounds-checked)
        if 0 < data_off < len(raw):
            preview_len = min(256, len(raw) - data_off)
            entry.raw = raw[data_off:data_off + preview_len]
            entry.text = _try_decode_text(entry.raw)

        data.entries.append(entry)
        index += 1
        offset += 20

        # Safety
        if index > 5000:
            data.parse_errors.append("Runaway entry count — aborting")
            break

    return data