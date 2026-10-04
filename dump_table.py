"""
Dump stringLiteral table entries around the endpoint and show the bytes each
one decodes to, so the {dataIndex,length} field order is unambiguous.
"""

import struct
from pathlib import Path

META = Path(
    r"C:\Users\hayden&eth\Desktop\le everything\EVERYTHING\1-Decompiled APKs\app"
    r"\assets\bin\Data\Managed\Metadata\global-metadata.dat"
)
ORIGINAL = b"https://eb1v6k1091.execute-api.us-west-1.amazonaws.com/"
TABLE_HIT = 134_980


def main():
    data = META.read_bytes()
    sl_off, sl_size = struct.unpack_from("<ii", data, 8)
    sld_off, sld_size = struct.unpack_from("<ii", data, 16)

    start = data.find(ORIGINAL)
    print(f"URL at file offset {start:,}, len {len(ORIGINAL)}, "
          f"dataIndex {start - sld_off:,}\n")

    # Print entries in a window, trying BOTH field orders so we can see which
    # interpretation yields sensible strings.
    print(f"{'pos':>8} {'int A':>9} {'int B':>9}   {'A=len,B=idx -> text':<52} {'B=len,A=idx -> text'}")
    print("-" * 150)
    for pos in range(TABLE_HIT - 32, TABLE_HIT + 33, 4):
        a, b = struct.unpack_from("<ii", data, pos)
        text_ab = text_ba = ""
        if 0 <= a < sld_size and 0 < b < sld_size:
            text_ab = data[sld_off + a:sld_off + a + b][:40]
        if 0 <= b < sld_size and 0 < a < sld_size:
            text_ba = data[sld_off + b:sld_off + b + a][:40]
        mark = "  <<<" if pos == TABLE_HIT else ""
        print(f"{pos:>8} {a:>9} {b:>9}   "
              f"{text_ab.decode('ascii','replace')!r:<52} "
              f"{text_ba.decode('ascii','replace')!r}{mark}")


if __name__ == "__main__":
    main()