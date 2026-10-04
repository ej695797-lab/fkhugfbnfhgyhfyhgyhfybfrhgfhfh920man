"""
Smoke test for the Yeeps private server.

Usage:
    python smoke_test.py [base_url]

Exercises all three emulated AWS services the game client talks to:
  1. Photon auth      -> GET  /?UserId=...&UserName=...
  2. Lambda           -> POST /2015-03-31/functions/{fn}/invocations
  3. DynamoDB         -> POST / with X-Amz-Target: DynamoDB_20120810.<Op>
  4. Direct API       -> POST /<handlerName>
"""

import json
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

PASSED = 0
FAILED = 0


def preflight(base):
    """Fail fast with a readable message when the API server is not running."""
    parsed = urllib.parse.urlparse(base)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        with socket.create_connection((host, port), timeout=3):
            pass
    except OSError as err:
        print(f"\nCannot reach {base} - {err}")
        print("\nThe API server is not running. Start it in a separate window:")
        print(f"    cd {Path(__file__).parent}")
        print("    python main.py")
        print("\nWait for 'Application startup complete.' then re-run this script.")
        return False
    return True


def call(method, path, body=None, headers=None):
    """Send a request and return (status, headers, text). Header lookup is case-insensitive."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, {k.lower(): v for k, v in err.headers.items()}, err.read().decode("utf-8", "replace")
    except urllib.error.URLError as err:
        return 0, {}, f"CONNECTION ERROR: {err}"


def check(name, ok, detail=""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name}\n        {detail}")


def test_photon_auth():
    print("\n[1] Photon auth")
    status, _, text = call("GET", "/?UserId=o_smoke&UserName=SmokeTester")
    body = json.loads(text) if text else {}
    check("GET / returns ResultCode 1", status == 200 and body.get("ResultCode") == 1, f"{status} {text[:200]}")
    check("UserId is rewritten to account$VR$name",
          body.get("UserId") == "o_smoke$VR$SmokeTester", str(body))


def test_lambda_login():
    print("\n[2] Lambda: questLogIntoAccount")
    payload = {
        "accountID": "o_smoke",
        "oculusID": "SmokeTester",
        "initialSkinColor": -3489025,
        "initialEyeColor": -2039846657,
        "propertiesToGet": ["currency", "roleKeys", "activeCosmetics", "serverTime"],
    }
    status, _, text = call("POST", "/2015-03-31/functions/g2_questLogIntoAccount/invocations", payload)
    envelope = json.loads(text) if text else {}
    check("envelope has statusCode 200", envelope.get("statusCode") == 200, text[:300])
    data = json.loads(envelope.get("body", "{}")) if envelope.get("body") else {}
    inner = data.get("data", {})
    check("account auto-created with displayName", inner.get("displayName") == "SmokeTester", str(inner)[:300])
    check("session fields present",
          all(k in inner for k in ("accessKey", "secretKey", "sessionToken", "gameSessionID")),
          str(list(inner.keys()))[:300])
    check("requested properties returned",
          all(k in inner for k in ("currency", "roleKeys", "activeCosmetics")), str(inner)[:300])


def test_lambda_room_data():
    print("\n[3] Lambda: fetchRoomData")
    payload = {"roomKey": "official_1", "propertiesToGet": ["roomName", "dimensions", "isCreative", "themeKey"]}
    status, _, text = call("POST", "/2015-03-31/functions/g2_fetchRoomData/invocations", payload)
    envelope = json.loads(text) if text else {}
    data = json.loads(envelope.get("body", "{}")) if envelope.get("body") else {}
    inner = data.get("data", {})
    check("roomName returned", inner.get("roomName") == "Starter House", str(inner)[:300])
    check("only requested properties returned", set(inner.keys()) == set(payload["propertiesToGet"]), str(inner)[:300])


def test_dynamo_get_item():
    print("\n[4] DynamoDB: GetItem G2_Globals")
    payload = {"TableName": "G2_Globals", "Key": {"key": {"S": "activeBundleKey"}}}
    status, headers, text = call("POST", "/", payload,
                                 {"X-Amz-Target": "DynamoDB_20120810.GetItem"})
    check("HTTP 200", status == 200, f"{status} {text[:200]}")
    check("content-type is x-amz-json-1.0",
          headers.get("content-type") == "application/x-amz-json-1.0", str(headers))
    body = json.loads(text) if text else {}
    item = body.get("Item", {})
    # G2_Globals is keyed on "key" and stores its payload in the "data" attribute.
    check("activeBundleKey data == bundle_commando",
          item.get("key", {}).get("S") == "activeBundleKey"
          and item.get("data", {}).get("S") == "bundle_commando", str(item)[:200])


def test_dynamo_batch_get():
    print("\n[5] DynamoDB: BatchGetItem G2_Rooms")
    payload = {
        "RequestItems": {
            "G2_Rooms": {
                "Keys": [{"roomKey": {"S": "tutorial"}}, {"roomKey": {"S": "official_1"}}],
                "AttributesToGet": ["roomKey", "roomName", "isOfficial"],
            }
        }
    }
    status, _, text = call("POST", "/", payload,
                           {"X-Amz-Target": "DynamoDB_20120810.BatchGetItem"})
    body = json.loads(text) if text else {}
    items = body.get("Responses", {}).get("G2_Rooms", [])
    check("two rooms returned", len(items) == 2, f"got {len(items)}: {text[:300]}")
    check("roomName is DynamoDB-typed (S)",
          all("S" in i.get("roomName", {}) for i in items), str(items)[:300])


def test_dynamo_update_roundtrip():
    print("\n[6] DynamoDB: UpdateItem then GetItem (write path)")
    payload = {
        "TableName": "G2_Accounts",
        "Key": {"accountID": {"S": "o_smoke"}},
        "AttributeUpdates": {"currency": {"Action": "PUT", "Value": {"N": "4242"}}},
    }
    status, _, text = call("POST", "/", payload,
                           {"X-Amz-Target": "DynamoDB_20120810.UpdateItem"})
    check("UpdateItem HTTP 200", status == 200, f"{status} {text[:200]}")

    read = {"TableName": "G2_Accounts", "Key": {"accountID": {"S": "o_smoke"}},
            "AttributesToGet": ["currency"]}
    status, _, text = call("POST", "/", read,
                           {"X-Amz-Target": "DynamoDB_20120810.GetItem"})
    body = json.loads(text) if text else {}
    currency = body.get("Item", {}).get("currency", {}).get("N")
    check("currency persisted as 4242", currency == "4242", str(body)[:200])


def test_direct_api():
    print("\n[7] Direct API route")
    payload = {"accountID": "o_direct", "oculusID": "DirectTester", "propertiesToGet": ["currency"]}
    status, _, text = call("POST", "/questLogIntoAccount", payload)
    body = json.loads(text) if text else {}
    check("HTTP 200", status == 200, f"{status} {text[:200]}")
    check("wrapped in data envelope", "data" in body, str(body)[:200])


def test_logs_written():
    print("\n[8] Traffic logging")
    log_dir = Path(__file__).parent / "logs"
    for name in ("http_traffic.log", "lambda_traffic.log", "login_traffic.log"):
        check(f"{name} exists", (log_dir / name).exists(), f"missing {log_dir / name}")


def main():
    print(f"Smoke testing {BASE}")
    if not preflight(BASE):
        return 2

    test_photon_auth()
    test_lambda_login()
    test_lambda_room_data()
    test_dynamo_get_item()
    test_dynamo_batch_get()
    test_dynamo_update_roundtrip()
    test_direct_api()
    test_logs_written()

    print("\n" + "=" * 50)
    print(f"  {PASSED} passed, {FAILED} failed")
    print("=" * 50)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())