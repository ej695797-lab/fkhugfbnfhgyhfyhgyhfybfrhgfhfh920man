# Yeeps Hide and Seek — Private Server API

FastAPI + MongoDB reimplementation of the original AWS **Lambda + DynamoDB** backend
for Yeeps Hide and Seek. The game client still speaks the original AWS protocol, so this
server inspects each request and dispatches it to the right emulated service.

## How it works

The game client talks to what it thinks are three separate AWS services. This server hosts
all three on one port and decides which one is being called by looking at the path, the
`Host` header, `Authorization`, and `X-Amz-Target`:

| # | Real AWS service | Detected by | Emulated by |
|---|---|---|---|
| 1 | Photon auth | `GET /?UserId=...` | `catch_all` in `main.py` |
| 2 | Lambda | `POST /2015-03-31/functions/{fn}/invocations` | `routers/lambda_router.py` → `handlers/` |
| 3 | DynamoDB | `X-Amz-Target: DynamoDB_20120810.<Op>` | `routers/dynamo_router.py` → `services/dynamo_ops.py` |
| 4 | Direct API (legacy) | `POST /<handlerName>` | `catch_all` → `HANDLER_TABLE` |

DynamoDB tables are mapped to MongoDB collections in `services/db.py`:

| DynamoDB table | Collection | Key |
|---|---|---|
| `G2_Accounts` | `accounts` | `accountID` |
| `G2_Rooms` | `rooms` | `roomKey` |
| `G2_RoomMap` | `room_maps` | `versionKey` |
| `G2_Maps` | `maps` | `mapKey` |
| `G2_PlayerStatuses` | `player_statuses` | `accountID` |
| `G2_Globals` | `globals` | `key` |
| `G2_Bundles` | `bundles` | `bundleKey` |

DynamoDB attribute typing (`{"S": "x"}`, `{"N": "1"}`, `{"L": [...]}`, `{"M": {...}}`) is
translated to/from plain JSON by `services/dynamo_types.py`, so the client sees valid
DynamoDB wire format.

## Requirements

- Python 3.10+
- MongoDB running on `localhost:27017`

## Setup

```powershell
# 1. Install dependencies
python -m pip install -r requirements.txt

# 2. Make sure MongoDB is running (it is set to Automatic, so usually already up)
sc query MongoDB | findstr STATE

# 3. Run the server — see the start/stop helpers below to avoid console-close issues
python main.py
```

You should see:

```
[seed] Syncing room_maps (world grid)...
[seed]   -> Upserted primary world map (beta4)
[seed]   -> Upserted 20 rooms (+details)
============================================================
  Yeeps v1 Private Server is READY
============================================================
```

The server listens on `http://0.0.0.0:8000`.

### Start / stop helpers

| Script | What it does |
|---|---|
| `start_server.bat` | Launches the server in its own minimized window titled "Yeeps API Server". Closing your cmd window will **not** kill it. |
| `stop_server.bat` | Kills whatever holds port 8000, then prints MongoDB's state. |

This avoids the most common failure mode: running `python main.py` in a console and then
closing that console, which hard-kills the server with no shutdown message. The server
then refuses connections even though it previously printed "Uvicorn running".

If port 8000 is busy, `stop_server.bat` clears it. Manually:

```cmd
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

### Verify it works

```powershell
python smoke_test.py
```

This exercises all four entry points and should report `20 passed, 0 failed`. If the
server is down it prints a short "not running" message instead of a traceback.

## Configuration

All settings live in `.env` and are read by `config.py`:

```ini
MONGO_URI=mongodb://localhost:27017
DB_NAME=OGYeeps
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
SEED_DB=1
RELOAD=0
```

| Variable | Default | Meaning |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017` | Mongo connection string |
| `DB_NAME` | `OGYeeps` | Database name |
| `SERVER_HOST` / `SERVER_PORT` | `0.0.0.0` / `8000` | Bind address |
| `SEED_DB` | `0` | `1` seeds rooms/globals/bundles on startup (idempotent — safe to leave on) |
| `RELOAD` | `0` | `1` enables auto-reload for development |

## Managing rooms

`mongosh` is not required — `manage_rooms.py` uses the same `services/db.py` connection
as the API. **No restart is needed; changes apply immediately.**

```powershell
python manage_rooms.py list
python manage_rooms.py show official_1
python manage_rooms.py add my_room --name "My Room" --theme suburb --dims 80 80 80
python manage_rooms.py add sandbox_1 --creative --player --dims 120 40 120
python manage_rooms.py copy official_1 my_house
python manage_rooms.py delete my_room
python manage_rooms.py complete
```

| Flag | Effect |
|---|---|
| `--name` | Display name (defaults to the roomKey) |
| `--theme` | Theme key (default `suburb`) |
| `--dims X Y Z` | Room dimensions (default `80 80 80`) |
| `--creative` | `isCreative=1`, `isModeLocked=0` — sandbox style |
| `--player` | `isOfficial=0` — player-made rather than official |

Verify a room over the API:

```powershell
curl -X POST http://127.0.0.1:8000/2015-03-31/functions/g2_fetchRoomData/invocations `
  -H "Content-Type: application/json" `
  -d '{\"roomKey\":\"my_room\",\"propertiesToGet\":[\"roomName\",\"themeKey\"]}'
```

### `complete` — why you want it

The seed only writes ~6 fields per room (`roomKey`, `roomName`, `isOfficial`,
`lastEditedSessionID`, `roomDataVersion`, `lastValidSaveOffset`). Everything else is
filled in at request time by `handle_room_data`, and those fallbacks are roomKey-dependent
— `tutorial` gets one set, `official_1` another, everything else a third. So a room can
report a `themeKey` it never actually had.

`complete` backfills the missing fields, taking values from `handlers/rooms.py` first so
the stored document matches what the handler would have served anyway. It never
overwrites existing values.

## Default (admin) account profile

Every **newly created** account receives the profile in `data/account_profile.json`,
merged over the built-in `DEFAULT_ACCOUNT` template in `handlers/login.py`:

```json
{
  "roleKeys": ["owner", "admin", "staff", ...],
  "ownedPatterns": ["solid", "stripes", ...],
  "eyeColor": -16777216,
  "skinColor": -16777216,
  "currency": 100000,
  "loginStreakData": { "length": 3650, "currentTier": "diamond", ... }
}
```

- **Colours are packed ARGB ints** (`0xAARRGGBB`). `-16777216` = `0xFF000000` = opaque
  black. Existing defaults were `skinColor = -3489025` (`0xFFCAC2FF`) and
  `eyeColor = -2039846657` (`0x866A68FF`).
- **Client-supplied colours are ignored** when the profile sets `skinColor`/`eyeColor`.
  Remove a key from the JSON to fall back to what the client sends.
- **`ownedBundles` is not in the JSON** — it is populated at login from every document in
  the `bundles` collection, so newly added bundles are granted automatically.
- Keys beginning with `_` are ignored, so the file can carry `_comment` notes.

### Applying it to accounts that already exist

The profile only runs on first creation. To update existing accounts:

```powershell
python apply_profile.py             # dry run - shows what would change
python apply_profile.py --write     # apply
python apply_profile.py --write --account o_123
```

### Placeholder IDs

`roleKeys` and `ownedPatterns` are **empty on purpose**. No catalog of the real game IDs
exists on this machine — the captured DynamoDB log they would have come from
(`Refrences/dynamo.txt`) has been deleted. Inventing strings looks like an admin account
but does nothing, and may confuse the client.

The *field names* are confirmed real (they appear in login responses). Only the *values*
are unknown. The only verified cosmetic IDs currently known are in the profile's
`_knownRealIDs` block: `bundle_commando` -> `commando`, `explosiveGrenade_frag`.

### Discovering the real IDs

`discover.py` mines `logs/` for what the client actually asked for:

```powershell
python discover.py
python discover.py --min-count 2
```

It reports every `propertiesToGet` field, DynamoDB table name, Lambda function name, and
account field name seen in traffic. Boot the game against this server, play for a bit,
then run it — any field you expected but never see is one you guessed wrong. Add real
values to `data/account_profile.json` when you find them.

Note that until you connect a real client, this only reflects traffic you generated
yourself (e.g. `smoke_test.py`).

## Logging

Every request is appended to `logs/`, so you can diff your server against the real one:

| File | Contents |
|---|---|
| `logs/http_traffic.log` | Every request/response, method, path, status |
| `logs/lambda_traffic.log` | Lambda invoke payloads |
| `logs/login_traffic.log` | Login payloads |

These files are your reference for filling in correct field values. The console also prints
which service handled each request, which is the fastest way to debug routing.

## Common requests

**Photon auth**
```powershell
curl "http://127.0.0.1:8000/?UserId=o_123&UserName=Tester"
# {"ResultCode":1,"UserId":"o_123$VR$Tester"}
```

**Lambda — log into an account (auto-creates on first login)**
```powershell
curl -X POST http://127.0.0.1:8000/2015-03-31/functions/g2_questLogIntoAccount/invocations `
  -H "Content-Type: application/json" `
  -d '{\"accountID\":\"o_123\",\"oculusID\":\"Tester\",\"propertiesToGet\":[\"currency\"]}'
```

Lambda responses use the double-JSON AWS envelope:
`{"statusCode":200,"headers":{...},"body":"<json string>"}`.

**Lambda — fetch room data**
```powershell
curl -X POST http://127.0.0.1:8000/2015-03-31/functions/g2_fetchRoomData/invocations `
  -H "Content-Type: application/json" `
  -d '{\"roomKey\":\"official_1\",\"propertiesToGet\":[\"roomName\",\"dimensions\"]}'
```

**DynamoDB — GetItem**
```powershell
curl -X POST http://127.0.0.1:8000/ `
  -H "Content-Type: application/json" `
  -H "X-Amz-Target: DynamoDB_20120810.GetItem" `
  -d '{\"TableName\":\"G2_Globals\",\"Key\":{\"key\":{\"S\":\"activeBundleKey\"}}}'
```

**DynamoDB — BatchGetItem**
```powershell
curl -X POST http://127.0.0.1:8000/ `
  -H "Content-Type: application/json" `
  -H "X-Amz-Target: DynamoDB_20120810.BatchGetItem" `
  -d '{\"RequestItems\":{\"G2_Rooms\":{\"Keys\":[{\"roomKey\":{\"S\":\"tutorial\"}}]}}}'
```

Supported DynamoDB operations: `GetItem`, `BatchGetItem`, `UpdateItem`, `PutItem`,
`DeleteItem`, `Query` (stub), `Scan` (stub), `DescribeTable`.

## Implemented Lambda functions

Matched by substring against the function name in `routers/lambda_router.py`:

| Function | Handler |
|---|---|
| `g2_questLogIntoAccount` | `handlers/login.py` |
| `g2_fetchRoomData` / `g2_getRoomData` | `handlers/rooms.py` |
| `g2_cwGetCanEnter` | `handlers/community.py` |
| `g2_cwTrackVisit` | `handlers/community.py` |
| `g2_cwTryPurchaseFuel` | `handlers/community.py` |
| `g2_cwEditPermissions` | `handlers/community.py` |
| `g2_putActiveCosmetics` | `handlers/cosmetics.py` |
| `g2_saveRoomMapCompressed` | `handlers/maps.py` |
| `g2_devResetCurrency` | `handlers/currency.py` |
| `g2_redeemChallengeReward` | `handlers/challenges.py` |
| `g2_fetchGlobalRotation` | `handlers/challenges.py` |
| `g2_fetchFeaturedWorldList` | `handlers/misc.py` |
| `g2_fetchPopularWorldList` | `handlers/misc.py` |
| `g2_logDebug` | `handlers/misc.py` |
| `g2_refreshAccountOnline` | `handlers/misc.py` |
| `g2_tryRedeemCurrencyStash` | `handlers/misc.py` |

Any unrecognised function falls through to a generic handler that returns
`propertiesToGet` defaults via `services/property_defaults.py`, so unknown calls still
return a well-formed envelope instead of failing.

## Project layout

```
main.py                  FastAPI app, service detection, traffic logging middleware
config.py                .env loading and settings
smoke_test.py            end-to-end check of all four entry points
manage_rooms.py          room admin CLI (list/show/add/copy/delete/complete)
apply_profile.py         apply the admin account profile to existing accounts
discover.py              mine traffic logs for the real game IDs the client uses
data/account_profile.json  default account template (roles, colours, currency, streak)
start_server.bat         launch detached so closing the console won't kill it
stop_server.bat          free port 8000 and report MongoDB state
routers/
  lambda_router.py       /2015-03-31/functions/{fn}/invocations + HANDLER_TABLE
  dynamo_router.py       /dynamodb
  photon.py              standalone Photon auth (superseded by catch_all in main.py)
handlers/                one module per feature area, each returns a plain dict
services/
  db.py                  Mongo client, collection accessors, DynamoDB table map
  dynamo_ops.py          GetItem/BatchGetItem/UpdateItem/PutItem/DeleteItem + fallbacks
  dynamo_types.py        DynamoDB typed-value <-> plain JSON conversion
  property_defaults.py   defaults for propertiesToGet fields
  replay_log.py          stub for replaying captured responses
seed/
  seed_db.py             idempotent seeding of rooms, globals, bundles, maps
  parse_dynamo.py        extracts seed data from a captured dynamo log
  default_room_map.json  the world map grid
logs/                    request/response logs (gitignored)
```

## Optional: captured-traffic seeding

`seed/seed_db.py` will additionally import real data if you drop these files in place:

- `Refrences/dynamo.txt` — captured DynamoDB responses
- `save.txt` — a captured `G2_Maps` save payload

Both are optional; seeding skips them cleanly when absent. `services/replay_log.py` is a
stubbed hook intended for replaying exact captured responses — currently a no-op that
always returns `None` so the real handlers run.