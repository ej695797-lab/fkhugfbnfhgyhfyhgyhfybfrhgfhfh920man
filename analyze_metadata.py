"""
Parse IL2CPP global-metadata.dat to locate the API endpoint string literal.

IL2CPP stores string literals in two places:
  * stringLiteral      - array of { int32 dataIndex; int32 length; }
  * stringLiteralData  - the raw UTF-8 bytes

The length is explicit, so replacing the URL with a DIFFERENT length requires
updating the length field, not just overwriting bytes.
"""

import struct
from pathlib import Path

META = Path(
    r"C:\Users\hayden&eth\Desktop\le everything\EVERYTHING\1-Decompiled APKs\app"
    r"\assets\bin\Data\Managed\Metadata\global-metadata.dat"
)

MAGIC = 0xFAB11BAF
NEEDLE = b"eb1v6k1091.execute-api.us-west-1.amazonaws.com"


def main():
    data = META.read_bytes()
    print(f"file size : {len(data):,} bytes")

    magic, version = struct.unpack_from("<II", data, 0)
    print(f"magic     : 0x{magic:08X} ({'ok' if magic == MAGIC else 'UNEXPECTED'})")
    print(f"version   : {version}")
    if magic != MAGIC:
        return

    # v24+ header: magic, version, then offset/size pairs
    (sl_off, sl_size, sld_off, sld_size) = struct.unpack_from("<iiii", data, 8)
    print(f"stringLiteral     : off={sl_off:,} size={sl_size:,}")
    print(f"stringLiteralData : off={sld_off:,} size={sld_size:,}")

    # Locate every occurrence of the needle
    hits = []
    start = 0
    while True:
        i = data.find(NEEDLE, start)
        if i < 0:
            break
        hits.append(i)
        start = i + 1
    print(f"\nneedle occurrences: {len(hits)}")
    for i in hits:
        print(f"  file offset {i:,}  (dataIndex {i - sld_off:,})")

    # Dump the surrounding bytes to see if a length prefix/terminator exists
    for i in hits:
        lo, hi = max(0, i - 24), min(len(data), i + len(NEEDLE) + 24)
        ctx = data[lo:hi]
        print(f"\ncontext around {i:,}:")
        print(f"  bytes[-24:]  {data[i-24:i].hex(' ')}")
        print(f"  needle       {data[i:i+len(NEEDLE)].hex(' ')}")
        print(f"  bytes[+0:]   {data[i+len(NEEDLE):i+len(NEEDLE)+16].hex(' ')}")

    # Scan the stringLiteral table for entries pointing at our dataIndex
    entry_count = sl_size // 8
    print(f"\nstringLiteral entries: {entry_count:,} (size {sl_size:,} / 8)")

    targets = {i - sld_off for i in hits}
    matched = []
    for e in range(entry_count):
        data_index, length = struct.unpack_from("<ii", data, sl_off + e * 8)
        if data_index in targets:
            matched.append((e, data_index, length))

    print(f"table entries referencing the endpoint: {len(matched)}")
    for e, data_index, length in matched:
        print(f"  entry[{e}] dataIndex={data_index:,} length={length}")
        if length != len(NEEDLE):
            print(f"    !! length field disagrees with needle ({len(NEEDLE)})")

    if matched:
        lens = {m[2] for m in matched}
        print(f"\ndistinct stored lengths: {lens}")
        print(f"needle byte length    : {len(NEEDLE)}")
        print(f"entries share one length: {len(lens) == 1}")


if __name__ == "__main__":
    main()