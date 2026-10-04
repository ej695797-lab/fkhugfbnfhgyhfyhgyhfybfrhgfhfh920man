"""
Map saving handler: g2_saveRoomMapCompressed
Stores map data with version history.
"""

from datetime import datetime, timezone

from services.db import maps


async def handle_save_room_map(body: dict) -> dict:
    """
    Save compressed room map data.
    Stores the current version and updates room metadata to trigger client reloads.
    """
    account_id = body.get("accountID", "")
    room_key = body.get("roomKey", "")
    map_data = body.get("mapData", "")
    internal_states = body.get("internalStates", "")
    map_data_version = body.get("mapDataVersion", 2)
    game_session_id = body.get("gameSessionID", "")
    app_version = body.get("applicationVersion", "")

    if not room_key:
        return {"success": 0}

    timestamp = datetime.now(timezone.utc).strftime("%Y %m/%d %H:%M:%S")

    # 1. Update the 'maps' collection (G2_Maps)
    map_key = f"{room_key}$current"
    current_doc = {
        "mapKey": map_key,
        "roomKey": room_key,
        "saveData": map_data,
        "saveInternalStates": internal_states,
        "mapDataVersion": map_data_version,
        "savedBy": account_id,
        "gameSessionID": game_session_id,
        "applicationVersion": app_version,
        "savedAt": timestamp,
    }

    await maps.update_one(
        {"mapKey": map_key},
        {"$set": current_doc},
        upsert=True,
    )

    # 2. Update the 'rooms' collection (G2_Rooms metadata)
    # This is vital so clients know the map has changed
    from services.db import rooms
    await rooms.update_one(
        {"roomKey": room_key},
        {
            "$set": {
                "lastEditedSessionID": int(game_session_id) if game_session_id.isdigit() else game_session_id,
                "roomDataVersion": map_data_version
            }
        },
        upsert=False # Only update if room exists
    )

    # 3. Save a versioned snapshot for history
    version_key = f"{room_key}$v_{timestamp.replace(' ', '_').replace('/', '-').replace(':', '-')}"
    history_doc = dict(current_doc)
    history_doc["mapKey"] = version_key
    history_doc["isHistorical"] = True

    await maps.update_one(
        {"mapKey": version_key},
        {"$set": history_doc},
        upsert=True,
    )

    print(f"[maps] Saved map for {room_key} by {account_id} (version: {map_data_version})")
    return {"success": 1}
