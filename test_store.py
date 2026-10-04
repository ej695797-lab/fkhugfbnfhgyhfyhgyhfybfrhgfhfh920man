"""Verify FileCollection matches the motor behaviours the handlers rely on."""

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.store import FileCollection

FAILS = []


def check(label, got, want):
    if got == want:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}\n          got:  {got!r}\n          want: {want!r}")
        FAILS.append(label)


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="yeeps-store-test-"))
    try:
        col = FileCollection(tmp, "rooms")

        check("empty find_one -> None", await col.find_one({"roomKey": "x"}), None)
        check("empty count", await col.count_documents({}), 0)

        r = await col.insert_one({"roomKey": "tutorial", "roomName": "Tutorial", "dims": [10, 10]})
        check("insert_one returns _id", bool(r.inserted_id), True)

        await col.insert_one({"roomKey": "official_0", "roomName": "Playground"})
        await col.insert_one({"roomKey": "custom", "roomName": "Custom", "cw_visits_total": 0})

        check("count after inserts", await col.count_documents({}), 3)

        doc = await col.find_one({"roomKey": "tutorial"})
        check("find_one by equality", doc["roomName"], "Tutorial")

        check("find_one projection exclude _id", "_id" in (await col.find_one({"roomKey": "tutorial"}, {"_id": 0})), False)
        check("find_one projection include", await col.find_one({"roomKey": "tutorial"}, {"_id": 0, "roomKey": 1}), {"roomKey": "tutorial"})

        check("missing field in filter -> None", await col.find_one({"roomKey": "nope"}), None)
        check("multi-key filter miss", await col.find_one({"roomKey": "tutorial", "roomName": "Wrong"}), None)
        check("multi-key filter hit", (await col.find_one({"roomKey": "tutorial", "roomName": "Tutorial"}))["dims"], [10, 10])

        found = await col.find({}).to_list(length=500)
        check("find all", len(found), 3)

        ordered = await col.find({}, {"_id": 0}).sort("roomKey", 1).to_list(length=500)
        check("sort ascending", [d["roomKey"] for d in ordered], ["custom", "official_0", "tutorial"])

        desc = await col.find({}, {"_id": 0}).sort("roomKey", -1).to_list(length=500)
        check("sort descending", [d["roomKey"] for d in desc], ["tutorial", "official_0", "custom"])

        lim = await col.find({}).to_list(length=2)
        check("to_list honours length", len(lim), 2)

        nested = await col.insert_one({"roomKey": "deep", "meta": {"a": 1}, "list": [1, 2]})
        check("dot-path equality", (await col.find_one({"meta.a": 1}))["roomKey"], "deep")

        await col.update_one({"roomKey": "tutorial"}, {"$set": {"roomName": "Renamed", "mode_locked": 0}})
        check("$set applies", (await col.find_one({"roomKey": "tutorial"}))["roomName"], "Renamed")
        check("$set adds new field", (await col.find_one({"roomKey": "tutorial"}))["mode_locked"], 0)

        await col.update_one({"roomKey": "custom"}, {"$inc": {"cw_visits_total": 1}})
        await col.update_one({"roomKey": "custom"}, {"$inc": {"cw_visits_total": 1}})
        check("$inc accumulates", (await col.find_one({"roomKey": "custom"}))["cw_visits_total"], 2)

        await col.update_one({"roomKey": "custom"}, {"$inc": {"never_seen": 5}})
        check("$inc on missing field starts at 0", (await col.find_one({"roomKey": "custom"}))["never_seen"], 5)

        up = await col.update_one({"roomKey": "brand_new"}, {"$set": {"roomName": "Fresh"}}, upsert=True)
        check("upsert sets upserted_id", bool(up.upserted_id), True)
        check("upsert creates doc", (await col.find_one({"roomKey": "brand_new"}))["roomName"], "Fresh")

        up2 = await col.update_one({"roomKey": "brand_new"}, {"$set": {"roomName": "Again"}})
        check("update hit reports matched", up2.matched_count, 1)
        check("update hit reports no upsert", up2.upserted_id, None)

        miss = await col.update_one({"roomKey": "absent"}, {"$set": {"x": 1}})
        check("update miss without upsert", (miss.matched_count, miss.upserted_id), (0, None))

        d = await col.delete_one({"roomKey": "deep"})
        check("delete_one removes", d.deleted_count, 1)
        check("delete_one deleted doc", await col.find_one({"roomKey": "deep"}), None)
        check("delete_one miss", (await col.delete_one({"roomKey": "deep"})).deleted_count, 0)

        # distinct
        b = FileCollection(tmp, "bundles")
        await b.insert_one({"bundleKey": "hat"})
        await b.insert_one({"bundleKey": "hat"})
        await b.insert_one({"bundleKey": "cape"})
        check("distinct dedupes", sorted(await b.distinct("bundleKey")), ["cape", "hat"])
        check("distinct on empty", await FileCollection(tmp, "empty").distinct("bundleKey"), [])

        # returned docs must be copies: mutating them must not touch the store
        snapshot = await col.find_one({"roomKey": "tutorial"})
        snapshot["roomName"] = "MUTATED"
        check("find_one returns a copy", (await col.find_one({"roomKey": "tutorial"}))["roomName"], "Renamed")

        # persistence across instances
        reopened = FileCollection(tmp, "rooms")
        check("persists to disk", await reopened.count_documents({}), await col.count_documents({}))
        check("persisted value intact", (await reopened.find_one({"roomKey": "custom"}))["cw_visits_total"], 2)

        # corrupt file must not crash the server
        (tmp / "rooms.json").write_text("{not json", encoding="utf-8")
        recovered = FileCollection(tmp, "rooms")
        check("corrupt file starts empty", await recovered.count_documents({}), 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        raise SystemExit(1)
    print("all store tests passed")


asyncio.run(main())