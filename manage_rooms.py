"""
Room management CLI for the Yeeps private server.

Uses the same MongoDB connection as the API (services/db.py), so no mongosh needed.

Usage:
    python manage_rooms.py list
    python manage_rooms.py show official_1
    python manage_rooms.py add my_room --name "My Room" --theme suburb --dims 80 80 80
    python manage_rooms.py add sandbox_1 --creative --dims 120 40 120
    python manage_rooms.py delete my_room
    python manage_rooms.py copy official_1 my_room_copy

Changes are visible immediately - no API restart needed.
"""

import argparse
import asyncio
import json

from services.db import rooms


def room_template(room_key: str, name: str, theme: str, dims: list, official: int,
                  creative: int, mode_locked: int) -> dict:
    """Build a room document with every field the handlers expect."""
    return {
        "roomKey": room_key,
        "roomName": name,
        "isOfficial": official,
        "themeKey": theme,
        "dimensions": dims,
        "floorDepth": 0,
        "lobbyDirection": 1,
        "door_up": {"block": 0, "position": [0, 0]},
        "door_right": {"block": 0, "position": [0, 0]},
        "door_down": {"block": 0, "position": [0, 0]},
        "door_left": {"block": 0, "position": [0, 0]},
        "isCreative": creative,
        "isModeLocked": mode_locked,
        "isAutoCycling": 0,
        "autoCycleTimestamp": 0,
        "noSave": 0,
        "isDevLocked": 0,
        "isVisible": 1,
        "lastEditedSessionID": 1,
        "roomDataVersion": 1,
        "liquidType": 0,
        "liquidColor": "",
        "liquidLevel": 0,
        "itemRestrictionsIsWhiteList": 0,
        "itemRestrictionsGroupKeys": [],
        "minVersion": "1.1.0",
        "versionKey": "teams1",
    }


async def cmd_list(args):
    cursor = rooms.find({}, {"_id": 0}).sort("roomKey", 1)
    docs = await cursor.to_list(length=500)
    if not docs:
        print("No rooms found. Run the server once with SEED_DB=1, or add one:")
        print('    python manage_rooms.py add my_room --name "My Room"')
        return

    print(f"{len(docs)} rooms:\n")
    print(f"{'roomKey':<24} {'official':<9} {'creat':<6} {'dims':<16} name")
    print("-" * 78)
    for d in docs:
        dims = d.get("dimensions")
        dims_s = f"{dims[0]}x{dims[1]}x{dims[2]}" if isinstance(dims, list) and len(dims) == 3 else "-"
        print(f"{d.get('roomKey',''):<24} {d.get('isOfficial','-'):<9} "
              f"{d.get('isCreative','-'):<6} {dims_s:<16} {d.get('roomName','')}")


async def cmd_show(args):
    doc = await rooms.find_one({"roomKey": args.room_key}, {"_id": 0})
    if not doc:
        print(f"No room with roomKey '{args.room_key}'.")
        return
    print(json.dumps(doc, indent=2, default=str))


async def cmd_add(args):
    doc = room_template(
        room_key=args.room_key,
        name=args.name,
        theme=args.theme,
        dims=args.dims,
        official=0 if args.player else 1,
        creative=1 if args.creative else 0,
        mode_locked=0 if args.creative else 1,
    )
    existing = await rooms.find_one({"roomKey": args.room_key}, {"_id": 0, "roomKey": 1})
    await rooms.update_one({"roomKey": args.room_key}, {"$set": doc}, upsert=True)
    verb = "Updated" if existing else "Added"
    print(f"{verb} room '{args.room_key}' ({doc['roomName']})")


async def cmd_copy(args):
    doc = await rooms.find_one({"roomKey": args.source}, {"_id": 0})
    if not doc:
        print(f"No room with roomKey '{args.source}'.")
        return
    doc = dict(doc)
    doc["roomKey"] = args.target
    doc["roomName"] = args.name or f"{doc.get('roomName', args.source)} (copy)"
    await rooms.update_one({"roomKey": args.target}, {"$set": doc}, upsert=True)
    print(f"Copied '{args.source}' -> '{args.target}'")


async def cmd_delete(args):
    result = await rooms.delete_one({"roomKey": args.room_key})
    if result.deleted_count:
        print(f"Deleted room '{args.room_key}'")
    else:
        print(f"No room with roomKey '{args.room_key}'.")


async def cmd_complete(args):
    """
    Backfill fields that were never seeded.

    The seed only writes a handful of fields per room, so anything missing is
    filled in by handle_room_data at request time using roomKey-dependent
    defaults. That makes e.g. themeKey resolve to "tutorial" for most rooms.

    Values come from handlers.rooms first so the database matches what the
    handler would have served anyway, then from the generic template.
    Existing values are never overwritten.
    """
    from handlers.rooms import (
        NON_TUTORIAL_OVERRIDES, OFFICIAL_1_DEFAULTS, TUTORIAL_DEFAULTS,
    )

    def handler_defaults(room_key: str) -> dict:
        if room_key == "official_1":
            return dict(OFFICIAL_1_DEFAULTS)
        base = dict(TUTORIAL_DEFAULTS)
        if room_key != "tutorial":
            base.update(NON_TUTORIAL_OVERRIDES)
        return base

    docs = await rooms.find({}).to_list(length=1000)
    if not docs:
        print("No rooms to complete.")
        return

    changed = 0
    for doc in docs:
        existing = set(doc.keys())
        room_key = doc["roomKey"]

        merged = handler_defaults(room_key)
        merged.update(room_template(
            room_key=room_key,
            name=doc.get("roomName", room_key),
            theme=doc.get("themeKey") or merged.get("themeKey", "suburb"),
            dims=doc["dimensions"] if isinstance(doc.get("dimensions"), list) else [80, 80, 80],
            official=doc.get("isOfficial", 0),
            creative=doc.get("isCreative", 0),
            mode_locked=doc.get("isModeLocked", 0),
        ))

        missing = {k: v for k, v in merged.items() if k not in existing}
        if not missing:
            continue
        await rooms.update_one({"roomKey": room_key}, {"$set": missing})
        print(f"  {room_key:<24} +{len(missing)} fields: {', '.join(sorted(missing))}")
        changed += 1

    print(f"\nCompleted {changed} of {len(docs)} rooms.")
    if changed:
        print("Restart not required - changes apply immediately.")


def build_parser():
    parser = argparse.ArgumentParser(description="Manage rooms in the Yeeps private server.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all rooms").set_defaults(func=cmd_list)

    show = sub.add_parser("show", help="Print one room as JSON")
    show.add_argument("room_key")
    show.set_defaults(func=cmd_show)

    add = sub.add_parser("add", help="Add or update a room")
    add.add_argument("room_key")
    add.add_argument("--name", default=None, help="Display name (defaults to the roomKey)")
    add.add_argument("--theme", default="suburb", help="Theme key (default: suburb)")
    add.add_argument("--dims", type=int, nargs=3, default=[80, 80, 80],
                     metavar=("X", "Y", "Z"), help="Room dimensions (default: 80 80 80)")
    add.add_argument("--creative", action="store_true", help="Mark as a creative/sandbox room")
    add.add_argument("--player", action="store_true", help="Mark as unofficial (player-made)")
    add.set_defaults(func=cmd_add)

    copy_cmd = sub.add_parser("copy", help="Duplicate an existing room")
    copy_cmd.add_argument("source")
    copy_cmd.add_argument("target")
    copy_cmd.add_argument("--name", default=None)
    copy_cmd.set_defaults(func=cmd_copy)

    delete = sub.add_parser("delete", help="Delete a room")
    delete.add_argument("room_key")
    delete.set_defaults(func=cmd_delete)

    sub.add_parser("complete", help="Backfill fields missing from seeded rooms").set_defaults(func=cmd_complete)

    return parser


def main():
    args = build_parser().parse_args()
    if getattr(args, "name", None) is None and args.command == "add":
        args.name = args.room_key
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()