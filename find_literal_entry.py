"""
Locate the exact stringLiteral table entries for the API endpoint.

The literal blob is packed and deduplicated; each table entry carries an
explicit {dataIndex, length}. Earlier attempt was off by 8 bytes because the
string starts at 'https://', not at the hostname.
"""

import struct
from pathlib import Path

META = Path(
    r"C:\Users\hayden&eth\Desktop\le everything\EVERYTHING\1-Decompiled APKs\app"
    r"\assets\bin\Data\Managed\Metadata\global-metadata.dat"
)
HOST = b"eb1v6k1091.execute-api.us-west-1.amazonaws.com"
ORIGINAL = b"https://eb1v6k1091.execute-api.us-west-1.amazonaws.com/"


def main():
    data = META.read_bytes()

    sl_off, sl_size = struct.unpack_from("<ii", data, 8)
    sld_off, sld_size = struct.unpack_from("<ii", data, 16)
    print(f"stringLiteral     off={sl_off:,} size={sl_size:,}")
    print(f"stringLiteralData off={sld_off:,} size={sld_size:,}")

    start = data.find(ORIGINAL)
    print(f"\nfull URL at file offset {start:,}")
    print(f"  bytes there  : {data[start:start+len(ORIGINAL)].decode()!r}")
    print(f"  length       : {len(ORIGINAL)}")

    data_index = start - sld_off
    print(f"  dataIndex    : {data_index:,}")

    # Dump the strings immediately around it so we can see the neighbours.
    lo = max(sld_off, start - 120)
    hi = min(sld_off + sld_size, start + len(ORIGINAL) + 120)
    print(f"\nneighbours in blob: {data[lo:start].decode('ascii','replace')[-70:]!r}"
          f" ||| {data[start:hi].decode('ascii','replace')[:90]!r}")

    # Scan every table entry for one pointing at our dataIndex.
    count = sl_size // 8
    matched = []
    for e in range(count):
        d, length = struct.unpack_from("<ii", data, sl_off + e * 8)
        if d == data_index:
            matched.append((e, length))

    print(f"\nstringLiteral entries: {count:,}")
    print(f"entries with dataIndex {data_index:,}: {len(matched)}")
    for e, length in matched:
        print(f"  entry[{e:>6}] length={length}  (expected {len(ORIGINAL)})")

    # Also look for neighbours we could borrow space from: find the entry whose
    # dataIndex is closest after ours, to know the free gap.
    after = [(d, length, e) for e, (d, length) in
             ((e, struct.unpack_from("<ii", data, sl_off + e * 8)) for e in range(count))
             if d > data_index]
    after.sort()
    if after:
        nd, nl, ne = after[0]
        gap = nd - (data_index + len(ORIGINAL))
        print(f"\nnearest next literal: entry[{ne}] dataIndex={nd:,} length={nl}")
        print(f"gap after our string: {gap} bytes")

    # The second occurrence lives outside the literal blob - identify its section.
    second = data.find(HOST, start + len(ORIGINAL))
    print(f"\nsecond occurrence at {second:,} (outside stringLiteralData)")
    for i in range(0, 24, 2):
        off, size = struct.unpack_from("<ii", data, 8 + i * 4)
        if off <= second < off + size:
            print(f"  -> inside header pair [{i},{i+1}] off={off:,} size={size:,}")
            break
    ctx = data[second - 40:second + len(HOST) + 40]
    print(f"  context: {ctx!r}")


if __name__ == "__main__":
    main()