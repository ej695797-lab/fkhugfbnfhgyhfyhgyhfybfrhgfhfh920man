"""
DynamoDB operation handlers.
Translates DynamoDB API calls into MongoDB operations.
"""

import json
import zlib
import uuid
from pathlib import Path

from services.db import get_collection, get_key_field
from services.dynamo_types import unwrap_key, unwrap_attribute_updates, wrap_item, from_dynamo, to_dynamo
from services.property_defaults import default_for_property




def _aws_id() -> str:
    return uuid.uuid4().hex.upper()


def _make_response(payload: dict) -> tuple[str, dict]:
    """Build a DynamoDB-formatted response: body text + headers."""
    payload_text = json.dumps(payload)
    crc32 = str(zlib.crc32(payload_text.encode("utf-8")) & 0xFFFFFFFF)
    headers = {
        "Content-Type": "application/x-amz-json-1.0",
        "x-amzn-RequestId": _aws_id(),
        "x-amz-crc32": crc32,
    }
    return payload_text, headers


async def _get_fallback_doc(table_name: str, query: dict) -> dict:
    """Provide default documents for sensitive tables when missing from DB."""
    # 1. G2_RoomMap fallback (World map / grid)
    if table_name == "G2_RoomMap":
        v_key = query.get("versionKey")
        if isinstance(v_key, str) and (v_key.startswith("o_") or v_key.startswith("p_o_")):
            # If the key is "o_123", base is "p_o_123". If key is "p_o_123", base is "p_o_123".
            base_key = v_key if v_key.startswith("p_") else f"p_{v_key}"
            return {
                "versionKey": v_key,
                "data": [
                    {
                        "themeKey": "sandbox",
                        "gridPosition": [0, 0],
                        "roomKey": f"{base_key}_sandbox"
                    }
                ]
            }
        # Generic fallback for room map
        collection = get_collection("G2_RoomMap")
        if collection is not None:
            return await collection.find_one({"versionKey": "beta4"}, {"_id": 0})

    # 2. G2_Rooms fallback (Individual room data)
    if table_name == "G2_Rooms":
        room_key = query.get("roomKey")
        if isinstance(room_key, str):
            is_sandbox = room_key.startswith("o_") or room_key.startswith("p_o_")
            return {
                "roomKey": room_key,
                "roomName": "Sandbox" if is_sandbox else room_key,
                "isOfficial": 0 if is_sandbox else 1,
                "themeKey": "sandbox" if is_sandbox else "suburb",
                "dimensions": [100, 100, 100],
                "floorDepth": 0,
                "lobbyDirection": 1,
                "isCreative": 1 if is_sandbox else 0,
                "isModeLocked": 0,
                "noSave": 0,
                "lastEditedSessionID": 1,
                "roomDataVersion": 1,
            }

    # 3. G2_Maps fallback (Saved block data)
    if table_name == "G2_Maps":
        map_key = query.get("mapKey")
        if isinstance(map_key, str) and "$" in map_key:
            room_key_from_map = map_key.split("$", 1)[0]
            collection = get_collection("G2_Maps")
            if collection is not None:
                return await collection.find_one({"mapKey": f"{room_key_from_map}$current"}, {"_id": 0})

    # 4. G2_Globals fallback
    if table_name == "G2_Globals":
        key = query.get("key")
        if key == "activeBundleKey":
            return {"key": "activeBundleKey", "data": "bundle_commando"}
        return {"key": key, "data": 0}

    return None


async def handle_get_item(body: dict) -> tuple[str, dict]:
    """Handle DynamoDB GetItem operation."""
    table_name = body.get("TableName", "")
    key = body.get("Key", {})
    attrs_to_get = body.get("AttributesToGet", [])
    requested_attrs = list(attrs_to_get)

    collection = get_collection(table_name)
    query = unwrap_key(key)
    
    # 1. Database lookup
    doc = None
    if collection is not None:
        doc = await collection.find_one(query, {"_id": 0})

    # 2. Fallback logic
    if doc is None:
        doc = await _get_fallback_doc(table_name, query)

    # 3. Build item and post-process
    if doc:
        item = wrap_item(doc, requested_attrs if requested_attrs else None)
        
        # Specialized G2_Bundles logic (MinVersion, etc)
        if table_name == "G2_Bundles" and isinstance(doc, dict):
            if doc.get("bundleKey") == "bundle_commando":
                item["endTimestamp"] = {"S": "2025 02/20 07:00:00"}
                item["minVersion"] = {"S": "1.19.0"}
            elif "minVersion" in doc:
                item["minVersion"] = to_dynamo(doc["minVersion"])
    else:
        # Not found — initialize with NULLs to be filled by defaults
        item = {a: {"NULL": True} for a in requested_attrs}

    # Inject defaults for sensitive tables
    if table_name in ["G2_Rooms", "G2_Maps", "G2_Accounts", "G2_Bundles", "G2_Globals"] and item:
        for attr in list(item.keys()):
            # Special case for accounts
            if table_name == "G2_Accounts" and attr == "shouldForceRefresh":
                item[attr] = {"N": "0"}
                continue
            
            # General default injection
            if item[attr] == {"NULL": True}:
                item[attr] = to_dynamo(default_for_property(attr))

    if not item:
        return _make_response({})

    return _make_response({"Item": item})


async def handle_batch_get_item(body: dict) -> tuple[str, dict]:
    """Handle DynamoDB BatchGetItem operation."""
    request_items = body.get("RequestItems", {})
    responses = {}

    for table_name, table_req in request_items.items():
        collection = get_collection(table_name)
        keys = table_req.get("Keys", [])
        attrs_to_get = table_req.get("AttributesToGet", [])

        items = []
        for dynamo_key in keys:
            query = unwrap_key(dynamo_key)
            doc = None
            if collection is not None:
                doc = await collection.find_one(query, {"_id": 0})

            # Fallback logic
            if doc is None:
                doc = await _get_fallback_doc(table_name, query)

            # Build item
            if doc:
                item = wrap_item(doc, attrs_to_get if attrs_to_get else None)
            elif table_name in ["G2_Rooms", "G2_Maps", "G2_Accounts", "G2_Bundles", "G2_Globals"]:
                # If sensitive table and no doc, provide an empty item with NULLs (to be filled below)
                item = {a: {"NULL": True} for a in attrs_to_get}
            else:
                # For other tables, skip missing items (standard DynamoDB behavior)
                continue

            # Specialized logic (MinVersion, etc)
            if table_name == "G2_Bundles" and doc and isinstance(doc, dict):
                if doc.get("bundleKey") == "bundle_commando":
                    item["endTimestamp"] = {"S": "2025 02/20 07:00:00"}
                    item["minVersion"] = {"S": "1.19.0"}
                elif "minVersion" in doc:
                    item["minVersion"] = to_dynamo(doc["minVersion"])
            
            # Inject defaults for sensitive tables
            if table_name in ["G2_Rooms", "G2_Maps", "G2_Accounts", "G2_Bundles", "G2_Globals"] and item:
                for attr in list(item.keys()):
                    # Special case for accounts
                    if table_name == "G2_Accounts" and attr == "shouldForceRefresh":
                        item[attr] = {"N": "0"}
                        continue
                    
                    # General default injection
                    if item[attr] == {"NULL": True}:
                        item[attr] = to_dynamo(default_for_property(attr))
                            
            items.append(item)

        responses[table_name] = items

    return _make_response({
        "Responses": responses,
        "UnprocessedKeys": {},
    })

async def handle_update_item(body: dict) -> tuple[str, dict]:
    """Handle DynamoDB UpdateItem operation."""
    table_name = body.get("TableName", "")
    key = body.get("Key", {})
    updates = body.get("AttributeUpdates", {})

    collection = get_collection(table_name)
    if collection is not None:
        query = unwrap_key(key)
        set_fields = unwrap_attribute_updates(updates)
        if set_fields:
            # Merge key fields into the document for upsert
            set_fields.update(query)
            await collection.update_one(
                query,
                {"$set": set_fields},
                upsert=True,
            )

    return _make_response({})


async def handle_put_item(body: dict) -> tuple[str, dict]:
    """Handle DynamoDB PutItem operation."""
    table_name = body.get("TableName", "")
    item = body.get("Item", {})

    collection = get_collection(table_name)
    if collection is not None and item:
        # Convert DynamoDB-typed Item to plain doc
        doc = {}
        for k, v in item.items():
            doc[k] = from_dynamo(v)

        key_field = get_key_field(table_name)
        if key_field and key_field in doc:
            await collection.update_one(
                {key_field: doc[key_field]},
                {"$set": doc},
                upsert=True,
            )
        else:
            await collection.insert_one(doc)

    return _make_response({})


async def handle_delete_item(body: dict) -> tuple[str, dict]:
    """Handle DynamoDB DeleteItem operation."""
    table_name = body.get("TableName", "")
    key = body.get("Key", {})

    collection = get_collection(table_name)
    if collection is not None:
        query = unwrap_key(key)
        await collection.delete_one(query)

    return _make_response({})


async def handle_query(body: dict) -> tuple[str, dict]:
    """Handle DynamoDB Query operation (stub — returns empty)."""
    return _make_response({"Items": [], "Count": 0, "ScannedCount": 0})


async def handle_scan(body: dict) -> tuple[str, dict]:
    """Handle DynamoDB Scan operation (stub — returns empty)."""
    return _make_response({"Items": [], "Count": 0, "ScannedCount": 0})


async def handle_describe_table(body: dict) -> tuple[str, dict]:
    """Handle DynamoDB DescribeTable operation."""
    return _make_response({
        "Table": {
            "TableName": body.get("TableName", "Unknown"),
            "TableStatus": "ACTIVE",
            "ItemCount": 0,
        }
    })


# Operation dispatcher
OPERATION_HANDLERS = {
    "GetItem":       handle_get_item,
    "BatchGetItem":  handle_batch_get_item,
    "UpdateItem":    handle_update_item,
    "PutItem":       handle_put_item,
    "DeleteItem":    handle_delete_item,
    "Query":         handle_query,
    "Scan":          handle_scan,
    "DescribeTable": handle_describe_table,
}


async def dispatch_dynamo(target: str, body: dict) -> tuple[str, dict]:
    """
    Dispatch a DynamoDB operation by X-Amz-Target.
    Returns (body_text, headers).
    """
    op = (target or "").rsplit(".", 1)[-1]
    handler = OPERATION_HANDLERS.get(op)

    if handler:
        return await handler(body)

    # Unknown operation — return empty
    return _make_response({})
