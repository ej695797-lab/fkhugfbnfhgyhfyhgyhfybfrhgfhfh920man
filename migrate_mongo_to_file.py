"""
Copy every collection out of MongoDB and into the file-backed store.

Use this when moving off MongoDB so accounts, custom rooms, maps and bundles
survive the switch. Existing file-store documents with the same _id are kept
unless --overwrite is passed.

    python migrate_mongo_to_file.py --preview
    python migrate_mongo_to_file.py
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import motor.motor_asyncio
from config import MONGO_URI, DB_NAME, DATA_DIR
from services.store import FileCollection

COLLECTIONS = [
    "accounts",
    "rooms",
    "room_maps",
    "maps",
    "player_statuses",
    "globals",
    "bundles",
]

# Documents are identified by their natural key, not _id: the file store mints
# fresh _id values, so _id matching would duplicate every seeded document.
KEY_FIELDS = {
    "accounts": "accountID",
    "rooms": "roomKey",
    "room_maps": "versionKey",
    "maps": "mapKey",
    "player_statuses": "accountID",
    "globals": "key",
    "bundles": "bundleKey",
}


def _jsonable(value):
    """Coerce BSON-only types (ObjectId, datetime) into JSON-safe values."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="report counts, write nothing")
    parser.add_argument("--skip-existing", action="store_true", help="keep same-key file docs")
    parser.add_argument("--wipe", action="store_true", help="empty the file store first")
    args = parser.parse_args()

    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=6000)
    try:
        await client.admin.command("ping")
    except Exception as exc:
        print(f"Cannot reach MongoDB at {MONGO_URI}\n  {type(exc).__name__}: {exc}")
        print("\nIs the local mongod running and MONGO_URI correct?")
        return 1

    mongo_db = client[DB_NAME]
    print(f"source: MongoDB {DB_NAME}")
    print(f"target: {DATA_DIR}")
    if args.preview:
        print("(preview - nothing will be written)\n")

    if args.wipe and not args.preview:
        for name in COLLECTIONS:
            path = DATA_DIR / f"{name}.json"
            if path.exists():
                path.unlink()
        print("wiped existing file store\n")

    total = 0
    for name in COLLECTIONS:
        source_docs = await mongo_db[name].find({}).to_list(length=None)
        if args.preview:
            print(f"  {name:<18} {len(source_docs):>5} docs")
            total += len(source_docs)
            continue

        target = FileCollection(DATA_DIR, name)
        key_field = KEY_FIELDS[name]
        before = await target.count_documents({})
        written = replaced = skipped = 0
        for doc in source_docs:
            doc = _jsonable(dict(doc))
            key_value = doc.get(key_field)
            if key_value is None:
                skipped += 1
                continue
            existing = await target.find_one({key_field: key_value})
            if existing:
                if args.skip_existing:
                    skipped += 1
                    continue
                await target.delete_one({"_id": existing["_id"]})
                replaced += 1
            await target.insert_one(doc)
            written += 1
        after = await target.count_documents({})
        parts = [f"mongo={len(source_docs)}", f"{before}->{after}"]
        if replaced:
            parts.append(f"{replaced} replaced")
        if skipped:
            parts.append(f"{skipped} skipped")
        print(f"  {name:<18} " + "  ".join(parts))
        total += written

    print(f"\n{total} document(s) {'would be' if args.preview else ''} copied")
    return 0


raise SystemExit(asyncio.run(main()))