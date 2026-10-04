"""
Database layer.

Defaults to the bundled file-backed store so the server runs with no external
database. Point MONGO_URI at a real MongoDB host and the exact same collection
objects are served by motor instead, with no handler changes.
"""

import motor.motor_asyncio
from config import MONGO_URI, DB_NAME, DATA_DIR, USE_FILE_DB
from services.store import FileCollection

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0")
_is_remote = MONGO_URI.startswith(("mongodb://", "mongodb+srv://")) and not any(
    host in MONGO_URI for host in _LOCAL_HOSTS
)

if USE_FILE_DB in {"1", "true", "yes", "on", "file"}:
    BACKEND = "file"
elif USE_FILE_DB in {"0", "false", "no", "off", "mongo"}:
    BACKEND = "mongo"
else:
    BACKEND = "mongo" if _is_remote else "file"

print(f"[db] backend={BACKEND} db={DB_NAME}")

if BACKEND == "mongo":
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
else:
    client = None
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    class _DB:
        """Minimal stand-in so `db["name"]` works for both backends."""

        def __getitem__(self, name):
            return FileCollection(DATA_DIR, name)

    db = _DB()

# ─── Collection accessors ───────────────────────────────────────────────

accounts       = db["accounts"]        # Key: accountID
rooms          = db["rooms"]           # Key: roomKey
room_maps      = db["room_maps"]       # Key: versionKey
maps           = db["maps"]           # Key: mapKey
player_statuses = db["player_statuses"] # Key: accountID
globals_col    = db["globals"]         # Key: key
bundles        = db["bundles"]         # Key: bundleKey

# DynamoDB TableName → MongoDB collection mapping
TABLE_MAP = {
    "G2_Accounts":       accounts,
    "G2_Rooms":          rooms,
    "G2_RoomMap":        room_maps,
    "G2_Maps":           maps,
    "G2_PlayerStatuses": player_statuses,
    "G2_Globals":        globals_col,
    "G2_Bundles":        bundles,
}

# DynamoDB TableName → primary key field name
TABLE_KEY_FIELDS = {
    "G2_Accounts":       "accountID",
    "G2_Rooms":          "roomKey",
    "G2_RoomMap":        "versionKey",
    "G2_Maps":           "mapKey",
    "G2_PlayerStatuses": "accountID",
    "G2_Globals":        "key",
    "G2_Bundles":        "bundleKey",
}


def get_collection(table_name: str):
    """Get the MongoDB collection for a DynamoDB table name."""
    return TABLE_MAP.get(table_name)


def get_key_field(table_name: str) -> str:
    """Get the primary key field name for a DynamoDB table name."""
    return TABLE_KEY_FIELDS.get(table_name, "")
