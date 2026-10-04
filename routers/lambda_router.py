"""
Lambda invocation router.
Handles POST /2015-03-31/functions/{fn}/invocations
Dispatches to the appropriate handler based on function name.
"""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import Response

from config import LOG_DIR
from handlers.login import handle_login
from handlers.rooms import handle_room_data
from handlers.community import (
    handle_cw_get_can_enter,
    handle_cw_track_visit,
    handle_cw_try_purchase_fuel,
    handle_cw_edit_permissions,
)
from handlers.cosmetics import handle_put_active_cosmetics
from handlers.maps import handle_save_room_map
from handlers.currency import handle_dev_reset_currency
from handlers.challenges import (
    handle_redeem_challenge_reward,
    handle_fetch_global_rotation,
)
from handlers.misc import (
    handle_fetch_featured_world_list,
    handle_fetch_popular_world_list,
    handle_log_debug,
    handle_refresh_account_online,
    handle_try_redeem_currency_stash,
)
from services.property_defaults import default_for_property

router = APIRouter()
LAMBDA_LOG_FILE = LOG_DIR / "lambda_traffic.log"


def _append_lambda_log(function_name: str, request_body: dict, response_body_text: str) -> None:
    """Append Lambda request/response payloads (no headers) to a file."""
    LAMBDA_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = (
        f"[{timestamp}]\n"
        f"Function: {function_name}\n"
        f"RequestBody: {json.dumps(request_body, ensure_ascii=False)}\n"
        f"ResponseBody: {response_body_text}\n"
        f"{'=' * 80}\n"
    )
    with LAMBDA_LOG_FILE.open("a", encoding="utf-8") as log_file:
        log_file.write(entry)


def _lambda_envelope_payload(data: dict) -> dict:
    """Build the Lambda envelope payload object."""
    body_inner = json.dumps(data)
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": body_inner,
    }


def _lambda_envelope(data: dict) -> Response:
    """
    Wrap a response in the double-JSON Lambda envelope the client expects.
    Outer: {"statusCode": 200, "headers": {...}, "body": "<json-string>"}
    """
    envelope = _lambda_envelope_payload(data)
    headers = {
        "Content-Type": "application/json",
        "x-amzn-RequestId": uuid.uuid4().hex,
        "x-amzn-Remapped-Content-Length": "0",
        "X-Amz-Executed-Version": "$LATEST",
    }
    return Response(
        content=json.dumps(envelope),
        media_type="application/json",
        headers=headers,
    )


# ─── Handler dispatch table ────────────────────────────────────────
# Each entry: (substring to match in lowercase, handler coroutine)
HANDLER_TABLE = [
    ("logintoaccount",          handle_login),
    ("fetchglobalrotation",     handle_fetch_global_rotation),
    ("fetchfeaturedworldlist",   handle_fetch_featured_world_list),
    ("fetchpopularworldlist",   handle_fetch_popular_world_list),
    ("cwgetcanenter",           handle_cw_get_can_enter),
    ("cwtrackvisit",            handle_cw_track_visit),
    ("cwtrypurchasefuel",       handle_cw_try_purchase_fuel),
    ("cweditpermissions",       handle_cw_edit_permissions),
    ("redeemchallengereward",   handle_redeem_challenge_reward),
    ("putactivecosmetics",      handle_put_active_cosmetics),
    ("saveroommapcompressed",   handle_save_room_map),
    ("devresetcurrency",        handle_dev_reset_currency),
    ("getroomdata",             handle_room_data),
    ("fetchroomdata",           handle_room_data),
    ("logdebug",                handle_log_debug),
    ("refreshaccountonline",    handle_refresh_account_online),
    ("tryredeemcurrencystash",  handle_try_redeem_currency_stash),
]


async def _generic_fallback(body: dict) -> dict:
    """
    Generic fallback for unknown Lambda functions.
    If body has propertiesToGet → return defaults for each property.
    Otherwise → return success.
    """
    props = body.get("propertiesToGet", [])
    if props:
        data = {p: default_for_property(p) for p in props}
        return {"data": data}
    return {"data": {"success": 1}}


@router.post("/2015-03-31/functions/{function_name}/invocations")
async def lambda_invoke(function_name: str, request: Request):
    """Handle Lambda-style function invocations."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    fn_lower = function_name.lower()
    print(f"[lambda] Invoking: {function_name}")

    # Find matching handler
    for match_str, handler in HANDLER_TABLE:
        if match_str in fn_lower:
            result = await handler(body)
            # If handler returned {data: ...}, use as-is; otherwise wrap
            if "data" not in result:
                result = {"data": result}
            envelope_text = json.dumps(_lambda_envelope_payload(result), ensure_ascii=False)
            _append_lambda_log(function_name, body, envelope_text)
            return _lambda_envelope(result)

    # No match — use generic fallback
    print(f"[lambda] No handler for '{function_name}', using fallback")
    result = await _generic_fallback(body)
    envelope_text = json.dumps(_lambda_envelope_payload(result), ensure_ascii=False)
    _append_lambda_log(function_name, body, envelope_text)
    return _lambda_envelope(result)
