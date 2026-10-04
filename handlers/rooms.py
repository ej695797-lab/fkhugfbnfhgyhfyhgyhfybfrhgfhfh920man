"""
Room data handlers: g2_getRoomData / g2_fetchRoomData
"""

from services.db import rooms
from services.property_defaults import default_for_property


# Base defaults for the tutorial room
TUTORIAL_DEFAULTS = {
    "roomKey": "tutorial",
    "roomName": "Tutorial",
    "isOfficial": 1,
    "dimensions": [52, 20, 52],
    "floorDepth": 0,
    "lobbyDirection": 1,
    "door_up": {"block": 1, "position": [0, 0]},
    "door_right": {"block": 1, "position": [0, 0]},
    "door_down": {"block": 1, "position": [0, 0]},
    "door_left": {"block": 1, "position": [0, 0]},
    "isCreative": 0,
    "isModeLocked": 1,
    "isAutoCycling": 0,
    "autoCycleTimestamp": 0,
    "noSave": 1,
    "isDevLocked": 0,
    "lastEditedSessionID": 1,
    "roomDataVersion": 1,
    # Frequently requested optional room fields in older/newer clients
    "liquidType": 0,
    "liquidColor": "",
    "liquidLevel": 0,
    "itemRestrictionsIsWhiteList": 0,
    "itemRestrictionsGroupKeys": [],
    "minVersion": "1.1.0",
    "maxVersion": "",
    "versionKey": "teams1",
    "themeKey": "tutorial",
    "isVisible": 1,
}

# Overrides for non-tutorial rooms
NON_TUTORIAL_OVERRIDES = {
    "door_up": {"block": 0, "position": [0, 0]},
    "door_right": {"block": 0, "position": [0, 0]},
    "door_down": {"block": 0, "position": [0, 0]},
    "door_left": {"block": 0, "position": [0, 0]},
    "isCreative": 0,
    "isModeLocked": 0,
    "isAutoCycling": 0,
    "autoCycleTimestamp": 0,
    "noSave": 1,
    "isDevLocked": 0,
    "lastEditedSessionID": 1,
    "roomDataVersion": 1,
}

# Fallback payload for official_1 matching the older working traffic.
OFFICIAL_1_DEFAULTS = {
    "roomKey": "official_1",
    "roomName": "<color=yellow>920man is tuff</color>",
    "themeKey": "suburb",
    "dimensions": [80, 80, 80],
    "floorDepth": 9,
    "lobbyDirection": 1,
    "door_up": {"block": 0, "position": [0, 0]},
    "door_right": {"block": 0, "position": [0, 0]},
    "door_down": {"block": 0, "position": [0, 0]},
    "door_left": {"block": 0, "position": [0, 0]},
    "isCreative": 0,
    "isModeLocked": 0,
    "isAutoCycling": 0,
    "autoCycleTimestamp": 0,
    "noSave": 0,
    "isDevLocked": 0,
    "lastEditedSessionID": 1,
    "roomDataVersion": 1,
}


async def handle_room_data(body: dict) -> dict:
    """
    Fetch room data for a given roomKey.
    Tries MongoDB first, falls back to tutorial/non-tutorial defaults.
    """
    room_key = body.get("roomKey", "")
    props = body.get("propertiesToGet", [])

    # Try to get room from DB
    room_doc = None
    if room_key:
        room_doc = await rooms.find_one({"roomKey": room_key}, {"_id": 0})

    # Build base values
    if not room_key or room_key == "tutorial":
        base = dict(TUTORIAL_DEFAULTS)
    elif room_key == "official_1":
        base = dict(OFFICIAL_1_DEFAULTS)
    else:
        base = dict(TUTORIAL_DEFAULTS)
        base.update(NON_TUTORIAL_OVERRIDES)
        base["roomName"] = room_key

    # Merge in DB values
    if room_doc:
        base.update(room_doc)

    # Ensure requested properties are always present even if DB/defaults miss one.
    for p in props:
        if p not in base:
            base[p] = default_for_property(p)

    # Match legacy behavior: when propertiesToGet is provided, return only
    # those requested properties.
    if props:
        return {p: base[p] for p in props}
    return base
