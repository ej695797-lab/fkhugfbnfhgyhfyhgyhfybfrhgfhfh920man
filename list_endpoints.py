"""
List every URL / endpoint string in the IL2CPP string literal table,
so we know the complete set that may need repointing.
"""

import struct
from pathlib import Path

META = Path(
    r"C:\Users\hayden&eth\Desktop\le everything\EVERYTHING\1-Decompiled APKs\app"
    r"\assets\bin\Data\Managed\Metadata\global-metadata.dat"
)


def main():
    data = META.read_bytes()
    sl_off, sl_size = struct.unpack_from("<ii", data, 8)
    sld_off, sld_size = struct.unpack_from("<ii", data, 16)
    count = sl_size // 8

    seen = {}
    for i in range(count):
        length, data_index = struct.unpack_from("<ii", data, sl_off + i * 8)
        if length <= 0 or data_index < 0 or data_index + length > sld_size:
            continue
        raw = data[sld_off + data_index:sld_off + data_index + length]
        try:
            s = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        low = s.lower()
        if low.startswith(("http://", "https://", "wss://", "ws://")) or \
           "amazonaws.com" in low or "execute-api" in low or "photon" in low:
            seen.setdefault(s, []).append(i)

    print(f"{len(seen)} distinct endpoint-ish literals in {count:,} entries\n")
    for s, idxs in sorted(seen.items(), key=lambda kv: -len(kv[0])):
        tag = ""
        low = s.lower()
        if "amazonaws.com" in low or "execute-api" in low:
            tag = "  <-- API GATEWAY"
        elif "photon" in low:
            tag = "  <-- PHOTON"
        elif "ip-ranges" in low:
            tag = "  <-- AWS IP CHECK"
        print(f"  entry {idxs[0]:>6}  len={len(s):>4}  {s!r}{tag}")


if __name__ == "__main__":
    main()