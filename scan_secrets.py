"""
Scan tracked files for strings that GitHub push protection blocks on
(AWS access key IDs, secret keys, private keys, common token prefixes).
"""

import re
import subprocess
from pathlib import Path

PATTERNS = {
    "AWS access key ID": rb"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA|APKA)[0-9A-Z]{16}\b",
    "AWS secret (40 char)": rb"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{40}(?![A-Za-z0-9+/=])",
    "private key block": rb"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "GitHub token": rb"\bgh[pousr]_[A-Za-z0-9]{36,}\b",
    "Slack token": rb"\bxox[abprs]-[A-Za-z0-9-]{10,}\b",
    "Google API key": rb"\bAIza[0-9A-Za-z\-_]{35}\b",
}


def main():
    files = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.split()

    hits = 0
    for rel in files:
        p = Path(rel)
        try:
            data = p.read_bytes()
        except OSError:
            continue
        for name, pat in PATTERNS.items():
            for m in re.finditer(pat, data):
                line_no = data[:m.start()].count(b"\n") + 1
                token = m.group(0).decode("latin1")
                if len(token) > 24:
                    token = token[:12] + "..." + token[-6:]
                print(f"{rel}:{line_no}  [{name}]  {token}")
                hits += 1

    print(f"\n{hits} potential secret(s) in {len(files)} tracked files")


if __name__ == "__main__":
    main()