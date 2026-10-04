"""Locate the API endpoint string inside the decompiled APK."""

import os
from pathlib import Path

ROOT = Path(r"C:\Users\hayden&eth\Desktop\le everything\EVERYTHING\1-Decompiled APKs\app")

NEEDLES = {
    "utf8": b"eb1v6k1091.execute-api.us-west-1.amazonaws.com",
    "utf16": "eb1v6k1091.execute-api.us-west-1.amazonaws.com".encode("utf-16-le"),
    "host_only": b"execute-api.us-west-1",
    "https_utf16": "https://eb1v6k1091".encode("utf-16-le"),
    "https_utf8": b"https://eb1v6k1091",
}


def main():
    print(f"scanning {ROOT}\n")
    hits = {}
    for dirpath, _dirs, files in os.walk(ROOT):
        for name in files:
            fp = Path(dirpath) / name
            try:
                if fp.stat().st_size > 400_000_000:
                    continue
                data = fp.read_bytes()
            except OSError:
                continue
            found = {k: data.count(v) for k, v in NEEDLES.items() if data.count(v)}
            if found:
                hits[fp] = found

    if not hits:
        print("NO MATCHES -- string not found in this tree")
        return

    for fp, found in hits.items():
        rel = fp.relative_to(ROOT)
        size = fp.stat().st_size / 1048576
        print(f"{size:9.2f} MB  {found}")
        print(f"            {rel}")


if __name__ == "__main__":
    main()