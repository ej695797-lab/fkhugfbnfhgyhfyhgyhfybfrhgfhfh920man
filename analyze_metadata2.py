"""
Deeper analysis of the v29 metadata header and the endpoint string literal.

Goals:
  1. Validate the header by checking that declared sections actually look sane.
  2. Find the FULL string that contains the endpoint (not just the hostname).
  3. Locate the stringLiteral table entry so we know the stored length.
"""

import struct
from pathlib import Path

META = Path(
    r"C:\Users\hayden&eth\Desktop\le everything\EVERYTHING\1-Decompiled APKs\app"
    r"\assets\bin\Data\Managed\Metadata\global-metadata.dat"
)
NEEDLE = b"eb1v6k1091.execute-api.us-west-1.amazonaws.com"


def ascii_ratio(chunk):
    if not chunk:
        return 0.0
    good = sum(1 for b in chunk if 32 <= b < 127 or b in (0, 9, 10, 13))
    return good / len(chunk)


def main():
    data = META.read_bytes()
    magic, version = struct.unpack_from("<II", data, 0)
    print(f"size={len(data):,}  magic=0x{magic:08X}  version={version}\n")

    # Dump the first 24 ints so we can spot the section table by plausibility.
    print("first 24 header ints (offset -> value, sample of section):")
    ints = struct.unpack_from("<24i", data, 0)
    for i in range(0, 24, 2):
        off, size = ints[i], ints[i + 1]
        if 0 < off < len(data) and 0 < size < len(data):
            sample = data[off:off + 48]
            preview = "".join(chr(b) if 32 <= b < 127 else "." for b in sample)
            print(f"  [{i:2},{i+1:2}] off={off:>12,} size={size:>12,}  {preview[:48]!r}")
        else:
            print(f"  [{i:2},{i+1:2}] off={off:>12,} size={size:>12,}")

    # Validate by finding the null-terminated identifier string table.
    print("\nsearching for the identifier string table (dense ASCII + nulls)...")
    best = None
    for pair in range(0, 24, 2):
        off, size = ints[pair], ints[pair + 1]
        if not (0 < off < len(data) and 1000 < size < len(data)):
            continue
        r = ascii_ratio(data[off:off + 4000])
        if r > 0.95 and (best is None or size > best[1]):
            best = (off, size)
    print(f"  densest ASCII section: {best}")

    # The endpoint occurrence that lives inside the blob region.
    first = data.find(NEEDLE)
    print(f"\nfirst occurrence at file offset {first:,}")

    # Walk backwards to find the start of the containing string.
    # String literal blobs are packed with explicit lengths, so we look for the
    # 'https://' that begins this URL and confirm nothing URL-ish precedes it.
    start = data.rfind(b"https://", max(0, first - 200), first)
    print(f"  'https://' begins at {start:,} (delta {first - start})")
    pre = data[max(0, start - 60):start]
    print(f"  60 bytes before it: {pre!r}")

    # Walk forward to the end of this string. URL chars only.
    end = first + len(NEEDLE)
    while end < len(data) and (data[end] in b"/:?=&_%#@~+-.abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        end += 1
    full = data[start:end]
    print(f"  full string  : {full.decode('ascii', 'replace')!r}")
    print(f"  full length  : {len(full)}")

    # Find the next plausible string start to see what follows.
    nxt = data.find(b"https://", end)
    if 0 < nxt < end + 40:
        nxt_end = nxt
        while nxt_end < len(data) and data[nxt_end] not in b"\x00" and nxt_end - nxt < 80:
            nxt_end += 1
        print(f"  next string  : {data[nxt:nxt_end].decode('ascii','replace')!r}")


if __name__ == "__main__":
    main()