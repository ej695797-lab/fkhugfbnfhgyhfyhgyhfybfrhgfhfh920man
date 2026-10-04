"""
Handler for g2_questLogIntoAccount.
Auto-creates accounts on first login.
"""

import uuid
import secrets
import base64
import json
import string
from datetime import datetime, timezone
from pathlib import Path

from config import BASE_DIR, LOG_DIR
from services.db import accounts, bundles
from services.property_defaults import default_for_property

LOGIN_LOG_FILE = LOG_DIR / "login_traffic.log"

# Profile applied to every newly created account. Colours are packed ARGB
# ints (0xAARRGGBB); -16777216 is opaque black.
PROFILE_PATH = Path(BASE_DIR) / "data" / "account_profile.json"


def _credential_shaped(prefix: str, length: int) -> str:
    """
    Build a credential-shaped placeholder.

    The client treats these fields as AWS SigV4 credentials and signs its
    DynamoDB calls with them, but this server issues and accepts them itself,
    so only the shape matters. Generating them at runtime (instead of storing
    literals) keeps real-looking secrets out of version control - GitHub push
    protection rejects any commit containing an ASIA-prefixed key ID.
    """
    alphabet = string.ascii_uppercase + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(length - len(prefix)))
    return prefix + body


# Stable for the lifetime of the process, so a client that caches them keeps
# working until the server restarts.
ACCESS_KEY = _credential_shaped("ASIA", 20)
SECRET_KEY = _credential_shaped("", 40)


def _load_profile() -> dict:
    """Load the default account profile, ignoring keys that start with '_'."""
    try:
        raw = PROFILE_PATH.read_text(encoding="utf-8")
        return {k: v for k, v in json.loads(raw).items() if not k.startswith("_")}
    except FileNotFoundError:
        print(f"[login] Profile not found at {PROFILE_PATH}, using built-in defaults")
    except Exception as exc:
        print(f"[login] Failed to load profile: {exc}")
    return {}


async def _all_bundle_keys() -> list:
    """Every bundle key in the database, so players own all current bundles."""
    keys = await bundles.distinct("bundleKey")
    return sorted(k for k in keys if isinstance(k, str) and k)


def _server_time() -> str:
    """Current time in the game's format: 'YYYY MM/DD HH:mm:ss'"""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y %m/%d %H:%M:%S")


def _random_session_id() -> str:
    return str(uuid.uuid4().int % 100_000_000)


def _random_nonce() -> str:
    return base64.b64encode(secrets.token_bytes(16)).decode("ascii")


def _random_key(length: int = 48) -> str:
    return base64.b64encode(secrets.token_bytes(length)).decode("ascii")


def _append_login_log(request_body: dict, response_body: dict) -> None:
    """Append login request/response payloads (no headers) to a file."""
    LOGIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = (
        f"[{timestamp}]\n"
        f"RequestBody: {json.dumps(request_body, ensure_ascii=False)}\n"
        f"ResponseBody: {json.dumps(response_body, ensure_ascii=False)}\n"
        f"{'=' * 80}\n"
    )
    with LOGIN_LOG_FILE.open("a", encoding="utf-8") as log_file:
        log_file.write(entry)


# Default account template for new players
DEFAULT_ACCOUNT = {
    "displayName": "",
    "ownedPatterns": [],
    "activeCosmetics": [],
    "ownedBundles": [],
    "wishlist": [],
    "eyeColor": 0,
    "skinColor": -1,
    "mobileCode": "9200",
    "hasCreatorPack": 1,
    "hasUnlockedPrivateRooms": 1,
    "isIsolated": 0,
    "hasPendingMobileLogin": 0,
    "roleKeys": [],
    "currency": 0,
    "redeemedStashIDs": [],
    "cw_admin": [],
    "cw_staff": [],
    "cw_favorites": [],
    "cw_nextCanUseFreeFuelTimestamp": "1970 01/01 00:00:00",
    "analyticEventKeys": [],
    "firstLogin": "",
    "loginStreakFreezeTimestamp": "1970 01/01 00:00:00",
    "hasPendingWarning": 0,
    "shouldForceRefresh": 0,
    "isPermabanned": 0,
    "isMutebanned": 0,
    "remainingBanHours": 1,
    "banReason": "<color=blue>920Man's Yeeps</color>",
    "skipAttestation": 1,
    "lastChallengeRedeemedTime_login": "1970 01/01 00:00:00",
    "lastChallengeRedeemedTime_easy": "1970 01/01 00:00:00",
    "lastChallengeRedeemedTime_hard": "1970 01/01 00:00:00",
    "pendingMessages": [],
    "loginStreakData": {"length": 1, "currentTier": None, "nextTierThreshold": 3, "nextTier": "bronze"},
    "matchmakingSegment": None,
}


async def handle_login(body: dict) -> dict:
    """
    Process a login request. Auto-creates the account if it doesn't exist.
    Returns the 'data' payload (will be wrapped by the Lambda envelope).
    """
    account_id = body.get("accountID", "")
    oculus_id = body.get("oculusID", "")
    initial_skin = body.get("initialSkinColor", -3489025)
    initial_eye = body.get("initialEyeColor", -2039846657)
    props_to_get = body.get("propertiesToGet", [])

    # Look up or create account
    account = await accounts.find_one({"accountID": account_id}, {"_id": 0})

    if account is None:
        # Auto-create new account from the template + admin profile.
        profile = _load_profile()
        account = dict(DEFAULT_ACCOUNT)
        account.update(profile)

        # Own every bundle currently in the database.
        account["ownedBundles"] = await _all_bundle_keys()

        account["accountID"] = account_id
        account["displayName"] = oculus_id or account_id
        # Client-supplied colours only apply when the profile leaves them unset.
        if "skinColor" not in profile:
            account["skinColor"] = initial_skin
        if "eyeColor" not in profile:
            account["eyeColor"] = initial_eye
        account["firstLogin"] = _server_time()
        await accounts.insert_one({**account})
        print(f"[login] Created new account: {account_id} ({oculus_id}) "
              f"bundles={len(account['ownedBundles'])} "
              f"roles={len(account.get('roleKeys', []))}")
    else:
        print(f"[login] Existing account: {account_id}")

    # Build response from the full account payload to match legacy behavior.
    # Older clients often tolerate/expect additional fields beyond
    # propertiesToGet, so we include all known account fields.
    data = {k: v for k, v in account.items() if k != "accountID"}

    # Ensure requested properties always exist.
    for prop in props_to_get:
        if prop not in data:
            data[prop] = default_for_property(prop)

    # Always include session/auth fields
    data["serverTime"] = _server_time()
    data["gameSessionID"] = "52759867"
    data["publicSessionID"] = "64827527"
    data["challengeNonce"] = "-4DJfVUq6G0_glnZzeV8ng=="
    data["skipAttestation"] = 1
    data["accessKey"] = ACCESS_KEY
    data["secretKey"] = SECRET_KEY
    data["sessionToken"] = "IQoJb3JpZ2luX2VjEKT//////////wEaCXVzLXdlc3QtMSJGMEQCIGux7ko80bOc/A6uIGmqpS30/lrR+BnmX4MOvh3/QILuAiAOBM/D4cVQN6p6JJZOpkufXsa2kcGbsn2ugIADV6Py7yrHAgh9EAMaDDY3MzQ5MzU2Mzk1NSIMlwPaIA+3J2hs9HXxKqQC8uRuzR0yjH65TFEOvzruUIo3FKIK+1n8JkDY1ocNpJM2dbFhvO/8DCXd0P44OG/RF7H5CkMsr5M4S5GAf9AZfZrrGakyTQlfJDX3AElzIjci1h5FRdMtjxZxXTUze/A05r8q7giQ9p6AA3ztE0aQTQcHNMK3VoAU1dbr/+Vb/ctvGVNL8ghoXLPnkIy3/ACHxtZie1VwtmVeTJ3bbrGdjIET8PlIIH4RerAbALwOH54NVln4sWFduZWLMWSKKs65WoEwXRfaShzIsMnDzZqUK/P6Q3ZmtnKpD/1gM2sWF+zYcnj8r4chdROpXHWteaF7sB5JGGepetVAkZlbgDxo3gVIQXwL4WaXKjl8iyPD1hBPo+WQAt2qlTtmfR5ps8qhUZ956zD0yMa7BjrYAeGmBxUhgipjxgcVGnsNqU4a9CKP9l4FYWsVR4c6JqkNllSXG0AklAqGUBAcD5iBiPef0lGsugjCkbINfFNWIn4MMbM4Ez0O34YSpJL9hGjOFzz8RtWdH6eRlQmc3QPttj9LaQKNXrnyl7ibTikRLGMI2+m3ha0/nG8Ytx4iHIKLzGfYGNGlOLcVWJ1ehekkMpUAY7IdOYupiz4ZUByuWye32O9i8hXUVW14b6bGaN4IgDIwFKqOQkgE+UIn4XFfhrNUK8qhrPNj+7MuLvNUmzdQzPcJ4J1ERQ=="
    data["e_accessKey"] = "eRi9T0nMr6NzYfPn9atAYRULSDLM5hy5jzcjiDRO/x4wvzjE6/kjFW5Ygj1EupKZ"
    data["e_secretKey"] = "9YuDOxB0EHRYW0xu4OFzg5bMabZuV4U8fcTE7TVrJBsQfm16Ld0Ld0KJHjGP7758hb0uEznFuUjD2BS7caBnm66ThP4/27+FV6QVCqJOZziqwchMdagxogbQIDOKYG2P"


    result = {"data": data}
    _append_login_log(body, result)
    return result
