"""
Repoint the Yeeps API Gateway endpoint inside an IL2CPP global-metadata.dat.

IL2CPP stores C# string literals in a table of {int32 length, int32 dataIndex}
pairs pointing into a packed blob. Replacing a URL with a *different length*
therefore requires updating the length field as well as the bytes, otherwise
the game reads past the end of the new string.

Because every literal carries an explicit length, writing a SHORTER string in
place is safe: the leftover bytes become dead space and no other entry moves.

Usage:
    python patch_endpoint.py --url http://192.168.1.230:8000/
    python patch_endpoint.py --url https://192.168.1.230:8000/ --dry-run
"""

import argparse
import shutil
import struct
import sys
from pathlib import Path

DEFAULT_META = Path(
    r"C:\Users\hayden&eth\Desktop\le everything\EVERYTHING\1-Decompiled APKs\app"
    r"\assets\bin\Data\Managed\Metadata\global-metadata.dat"
)

ORIGINAL = "https://eb1v6k1091.execute-api.us-west-1.amazonaws.com/"


def find_entries(data, original, sld_off, sld_size):
    """Return [(entry_index, length_field_offset, data_offset, length)] matches."""
    needle = original.encode("utf-8")
    sl_off, sl_size = struct.unpack_from("<ii", data, 8)
    hits = []
    for i in range(sl_size // 8):
        length, data_index = struct.unpack_from("<ii", data, sl_off + i * 8)
        if length != len(needle) or data_index < 0 or data_index + length > sld_size:
            continue
        if data[sld_off + data_index:sld_off + data_index + length] == needle:
            hits.append((i, sl_off + i * 8, sld_off + data_index, length))
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True,
                    help="replacement base URL, must end with / and be <= original length")
    ap.add_argument("--meta", type=Path, default=DEFAULT_META, help="path to global-metadata.dat")
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    args = ap.parse_args()

    url = args.url
    if not url.endswith("/"):
        url += "/"

    meta = args.meta
    if not meta.is_file():
        sys.exit(f"not found: {meta}")

    original, replacement = ORIGINAL.encode(), url.encode()
    if len(replacement) > len(original):
        sys.exit(
            f"replacement is {len(replacement)} bytes, original is {len(original)}.\n"
            f"IL2CPP literals are length-prefixed; a longer string would overwrite\n"
            f"neighbouring literals. Use a shorter URL (or a hostname alias)."
        )

    data = bytearray(meta.read_bytes())
    magic, version = struct.unpack_from("<II", data, 0)
    sld_off, sld_size = struct.unpack_from("<ii", data, 16)
    print(f"metadata : {meta}")
    print(f"version  : {version} (magic 0x{magic:08X})")

    entries = find_entries(data, original.decode(), sld_off, sld_size)
    if not entries:
        sys.exit(f"literal not present in the stringLiteral table: {ORIGINAL}")

    print(f"\nfound {len(entries)} stringLiteral table entr(y/ies)\n")
    for idx, len_off, data_off, length in entries:
        print(f"  entry {idx}: length@{len_off} data@{data_off} len={length}")

    # Any raw copies outside the literal table (null-terminated name pools).
    raw_hits = []
    pos = 0
    while True:
        pos = data.find(original, pos)
        if pos < 0:
            break
        raw_hits.append(pos)
        pos += 1
    in_table = {d for _, _, d, _ in entries}
    extra = [p for p in raw_hits if p not in in_table]
    print(f"\nraw byte occurrences: {len(raw_hits)} "
          f"({len(entries)} in table, {len(extra)} elsewhere)")
    for p in extra:
        ctx = data[p - 12:p + len(original) + 12]
        print(f"  offset {p:,}: ...{ctx.decode('ascii', 'replace')!r}...")

    if args.dry_run:
        print("\nDRY RUN - nothing written")
        return

    backup = meta.with_suffix(".dat.bak")
    if not backup.exists():
        shutil.copy2(meta, backup)
        print(f"\nbackup   : {backup}")

    # 1. Patch the literal table: bytes + explicit length field.
    for idx, len_off, data_off, length in entries:
        data[data_off:data_off + len(replacement)] = replacement
        # Neutralise the tail of the old string so nothing can read stale text.
        for i in range(data_off + len(replacement), data_off + length):
            data[i] = 0
        struct.pack_into("<i", data, len_off, len(replacement))
        print(f"  patched entry {idx}: len {length} -> {len(replacement)}")

    # 2. Patch extra null-terminated copies (shorter write, so no overflow).
    for p in extra:
        data[p:p + len(replacement)] = replacement
        data[p + len(replacement)] = 0
        print(f"  patched raw copy at {p:,}")

    meta.write_bytes(bytes(data))

    # 3. Verify by re-reading the table.
    check = bytearray(meta.read_bytes())
    again = find_entries(check, original.decode(), sld_off, sld_size)
    if again:
        sys.exit("VERIFY FAILED: original literal still present")
    hits = find_entries(check, url, sld_off, sld_size)
    print(f"\nverify   : {len(hits)} entr(y/ies) now read {url!r}")
    for idx, len_off, data_off, length in hits:
        stored = bytes(check[data_off:data_off + length])
        print(f"  entry {idx}: {stored.decode('utf-8', 'replace')!r} (len {length})")
    print(f"\nOK - patched {meta}")


if __name__ == "__main__":
    main()