"""
Discover the real game IDs your client uses.

Everything in data/account_profile.json like roleKeys and ownedPatterns has to
match strings the real game recognises. Those strings are not in this repo, so
the reliable way to learn them is to watch what the client actually asks for.

This mines logs/ for:
  - every propertiesToGet field the client requested
  - every DynamoDB TableName
  - every Lambda function name
  - every account field the login response has ever contained

Usage:
    python discover.py
    python discover.py --min-count 2      # ignore one-off fields
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from config import LOG_DIR

FUNC_RE = re.compile(r"/2015-03-31/functions/([^/]+)/invocations")


def iter_log_entries(path: Path):
    """Yield (request_body_text, response_body_text) pairs from a log file."""
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    for block in text.split("=" * 80):
        req = re.search(r"RequestBody:\s*(.*)", block)
        resp = re.search(r"ResponseBody:\s*(.*)", block)
        path_m = re.search(r"Path:\s*(\S+)", block)
        yield (
            req.group(1).strip() if req else "",
            resp.group(1).strip() if resp else "",
            path_m.group(1) if path_m else "",
        )


def walk(obj, found, key_hint=""):
    """Recursively collect dict keys and string values."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.add(key)
            walk(value, found)
    elif isinstance(obj, list):
        for item in obj:
            walk(item, found)


def main(args):
    props = Counter()
    tables = Counter()
    funcs = Counter()
    account_fields = Counter()

    logs = sorted(LOG_DIR.glob("*.log"))
    if not logs:
        print(f"No logs in {LOG_DIR}")
        return

    total = 0
    for log in logs:
        for req_text, resp_text, path in iter_log_entries(log):
            total += 1
            if (m := FUNC_RE.search(path)):
                funcs[m.group(1)] += 1

            for text in (req_text, resp_text):
                if not text:
                    continue
                try:
                    data = json.loads(text)
                except Exception:
                    # Lambda bodies are double-encoded JSON strings.
                    try:
                        data = json.loads(json.loads(text).get("body", "{}"))
                    except Exception:
                        continue

                if isinstance(data, dict):
                    for name in data.get("propertiesToGet", []) or []:
                        if isinstance(name, str):
                            props[name] += 1
                    if isinstance(data.get("TableName"), str):
                        tables[data["TableName"]] += 1
                    for name in (data.get("RequestItems") or {}):
                        tables[name] += 1
                    if isinstance(data.get("data"), dict):
                        account_fields.update(data["data"].keys())

    print(f"Scanned {total} log entries across {len(logs)} file(s)\n")

    def show(title, counter, hint=""):
        kept = {k: v for k, v in counter.items() if v >= args.min_count}
        if not kept:
            return
        print(f"--- {title} ({len(kept)}) ---")
        if hint:
            print(f"    {hint}")
        for name, count in sorted(kept.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {count:>5}  {name}")
        print()

    show("propertiesToGet fields", props,
         "These are real account/room field names. Any you expected but never saw are wrong.")
    show("DynamoDB tables", tables)
    show("Lambda functions", funcs)
    show("Account fields returned", account_fields,
         "Field names present in login responses.")

    if not (props or tables or funcs or account_fields):
        print("Nothing discovered yet - no parsable entries in the logs.")
        print("Run the game against the server first, then re-run this.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mine traffic logs for real game IDs.")
    parser.add_argument("--min-count", type=int, default=1,
                        help="only show fields seen at least this many times")
    main(parser.parse_args())