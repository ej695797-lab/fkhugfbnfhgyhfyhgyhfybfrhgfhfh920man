"""
Apply the admin profile to existing accounts.

handlers/login.py only applies data/account_profile.json when an account is
FIRST created, so accounts that already logged in keep their old values.
This applies the same profile to accounts that already exist.

Usage:
    python apply_profile.py             # dry run, lists what would change
    python apply_profile.py --write     # actually apply
    python apply_profile.py --write --account o_123
"""

import argparse
import asyncio

from handlers.login import _all_bundle_keys, _load_profile
from services.db import accounts


async def main(args):
    profile = _load_profile()
    if not profile:
        print("Could not load data/account_profile.json")
        return

    profile["ownedBundles"] = await _all_bundle_keys()

    query = {"accountID": args.account} if args.account else {}
    docs = await accounts.find(query, {"_id": 0}).to_list(length=500)

    if not docs:
        print("No matching accounts.")
        return

    mode = "APPLYING" if args.write else "DRY RUN (use --write to apply)"
    print(f"{mode} profile to {len(docs)} account(s)\n")

    for doc in docs:
        changes = {}
        for key, value in profile.items():
            if doc.get(key) != value:
                changes[key] = value
        if not changes:
            print(f"  {doc.get('accountID'):<20} already up to date")
            continue
        print(f"  {doc.get('accountID'):<20} {len(changes)} change(s): "
              f"{', '.join(sorted(changes))}")
        if args.write:
            await accounts.update_one({"accountID": doc["accountID"]}, {"$set": changes})

    if args.write:
        print("\nDone. Re-login to pick up the new values.")
    else:
        print("\nNo changes written. Re-run with --write to apply.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply the admin profile to accounts.")
    parser.add_argument("--write", action="store_true", help="Actually write changes")
    parser.add_argument("--account", default=None, help="Limit to one accountID")
    asyncio.run(main(parser.parse_args()))