"""
Brute-force how the endpoint's blob offset is encoded in v29 metadata.

Rather than assume a table layout, search the whole file for the offset as a
little-endian int32 and report which regions contain it.
"""

import struct
from pathlib import Path

META = Path(
    r"C:\Users\hayden&eth\Desktop\le everything\EVERYTHING\1-Decompiled APKs\app"
    r"\assets\bin\Data\Managed\Metadata\global-metadata.dat"
)
ORIGINAL = b"https://eb1v6k1091.execute-api.us-west-1.amazonaws.com/"


def regions(data):
    """Header offset/size pairs, interpreted from byte 8 onward."""
    out = []
    for i in range(0, 48, 2):
        off, size = struct.unpack_from("<ii", data, 8 + i * 4)
        if 0 < off < len(data) and 0 < size <= len(data) - off:
            out.append((8 + i * 4, off, size))
    return out


def main():
    data = META.read_bytes()
    start = data.find(ORIGINAL)
    sl_off, sl_size = struct.unpack_from("<ii", data, 8)
    sld_off, sld_size = struct.unpack_from("<ii", data, 16)
    data_index = start - sld_off

    regs = regions(data)
    print(f"string starts at file offset {start:,}, length {len(ORIGINAL)}")
    print(f"stringLiteralData off={sld_off:,} -> dataIndex={data_index:,}\n")

    targets = {
        "dataIndex(blob-relative)": data_index,
        "file offset": start,
        "length": len(ORIGINAL),
    }

    for label, val in targets.items():
        needle = struct.pack("<i", val)
        positions = []
        idx = 0
        while True:
            p = data.find(needle, idx)
            if p < 0:
                break
            positions.append(p)
            idx = p + 1
        in_table = [p for p in positions if sl_off <= p < sl_off + sl_size]
        print(f"{label:<24} = {val:>10,}  found {len(positions):>4}x"
              f"  (in stringLiteral table: {len(in_table)})")
        for p in positions[:6]:
            where = "?"
            for hdr, off, size in regs:
                if off <= p < off + size:
                    where = f"section@{off:,}+{p - off:,}"
                    break
            print(f"      at {p:>12,}  {where}")
        if in_table:
            for p in in_table[:4]:
                ctx = struct.unpack_from("<6i", data, p - 8)
                print(f"      table ctx (2 ints before + 4): {ctx}")
        print()


if __name__ == "__main__":
    main()