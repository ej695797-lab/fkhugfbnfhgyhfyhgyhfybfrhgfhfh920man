"""
Yeeps v1 Private Server API

FastAPI stand-in for the original AWS Lambda + DynamoDB backend. Data lives in
MongoDB when MONGO_URI points at a real host, otherwise in a local JSON store.

The game client sends requests to three "services" all on the same host.
We detect which service by inspecting the path, headers, and host.
"""

import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import motor.motor_asyncio
from starlette.concurrency import iterate_in_threadpool

from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse

from config import (
    LOG_DIR, SEED_DB, SERVER_HOST, SERVER_PORT, RELOAD,
    USE_SSL, CERT_FILE, KEY_FILE, DATA_DIR,
    MONGO_URI, DB_NAME,
)
from routers.lambda_router import router as lambda_router
from routers.dynamo_router import router as dynamo_router
from seed.seed_db import seed_database
from services.replay_log import lookup_replay
from services.db import accounts, db, BACKEND
from handlers.login import GRADIENT_DISPLAY_NAME

HTTP_LOG_FILE = LOG_DIR / "http_traffic.log"


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Optionally seed the database, then announce readiness."""
    if SEED_DB:
        await seed_database()
    else:
        print("[seed] Skipped (set SEED_DB=1 in .env to enable)")
    print("=" * 60)
    print("  Yeeps v1 Private Server is READY")
    print("=" * 60)
    yield


app = FastAPI(title="Yeeps v1 Private Server", lifespan=lifespan)


@app.get("/health")
async def health():
    """
    Report which database backend is active and whether it is reachable.

    Every data-backed route fails with an opaque 500 when the database is down,
    so surface the real cause here rather than making the operator read
    platform logs.
    """
    info = {"backend": BACKEND, "db_name": DB_NAME}
    if BACKEND != "mongo":
        info["storage"] = str(DATA_DIR)
        try:
            info["rooms"] = await db["rooms"].count_documents({})
            info["accounts"] = await db["accounts"].count_documents({})
            info["status"] = "ok"
            return info
        except Exception as exc:
            info["status"] = f"FAILED: {type(exc).__name__}: {exc}"
            return JSONResponse(status_code=503, content=info)

    redacted = re.sub(r"//[^@]+@", "//***:***@", MONGO_URI)
    info["mongo_uri_host"] = redacted
    try:
        probe = motor.motor_asyncio.AsyncIOMotorClient(
            MONGO_URI, serverSelectionTimeoutMS=8000
        )
        await probe.admin.command("ping")
        info["rooms"] = await db["rooms"].count_documents({})
        info["status"] = "ok"
        return info
    except Exception as exc:
        info["status"] = f"FAILED: {type(exc).__name__}: {exc}"
        return JSONResponse(status_code=503, content=info)


def _safe_decode(payload: bytes) -> str:
    """Decode bytes for logging without throwing on binary data."""
    if not payload:
        return ""
    return payload.decode("utf-8", errors="replace")


def _append_http_log(entry: str) -> None:
    HTTP_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HTTP_LOG_FILE.open("a", encoding="utf-8") as log_file:
        log_file.write(entry)


@app.middleware("http")
async def log_http_traffic(request: Request, call_next):
    request_body = await request.body()
    request_body_text = _safe_decode(request_body)

    response = await call_next(request)

    response_chunks = [chunk async for chunk in response.body_iterator]
    response_body = b"".join(response_chunks)
    response_body_text = _safe_decode(response_body)

    # Rebuild response because we consumed body_iterator while logging.
    response.body_iterator = iterate_in_threadpool(iter([response_body]))

    now = datetime.now(timezone.utc).isoformat()
    full_path = str(request.url.path)
    if request.url.query:
        full_path = f"{full_path}?{request.url.query}"

    log_entry = (
        f"[{now}]\n"
        f"Client: {request.client.host if request.client else 'unknown'}\n"
        f"Method: {request.method}\n"
        f"Path: {full_path}\n"
        f"RequestBody: {request_body_text}\n"
        f"StatusCode: {response.status_code}\n"
        f"ResponseBody: {response_body_text}\n"
        f"{'=' * 80}\n"
    )
    _append_http_log(log_entry)

    return response


# ─── Debug helpers ─────────────────────────────────────────────────────
# Registered before the catch-all below, which would otherwise shadow them.

@app.get("/debug/traffic")
async def debug_traffic(lines: int = 60, body_chars: int = 600):
    """
    Return recent request/response pairs from the traffic log.

    Useful for working out which call the game client makes while loading a
    room, without needing shell access to the host.
    """
    if not HTTP_LOG_FILE.exists():
        return {"log_path": str(HTTP_LOG_FILE), "entries": [], "note": "no traffic yet"}
    text = HTTP_LOG_FILE.read_text(encoding="utf-8", errors="replace")
    chunks = [c for c in text.split("=" * 80) if c.strip()]
    parsed = []
    for chunk in chunks[-lines:]:
        entry = {}
        for line in chunk.strip().splitlines():
            if ": " in line:
                key, value = line.split(": ", 1)
                entry[key.strip()] = value.strip()
        if entry:
            entry["RequestBody"] = entry.get("RequestBody", "")[:body_chars]
            entry["ResponseBody"] = entry.get("ResponseBody", "")[:body_chars]
            parsed.append(entry)
    return {
        "log_path": str(HTTP_LOG_FILE),
        "total_entries": len(chunks),
        "returned": len(parsed),
        "entries": parsed,
    }


# ─── Startup ─────────────────────────────────────────────────────────

# ─── Include routers ─────────────────────────────────────────────────

# Lambda routes (specific path pattern)
app.include_router(lambda_router)

# DynamoDB routes. Registered at /dynamodb only — the bare "/" route was
# removed from the router because it shadowed the catch-all Photon auth path.
app.include_router(dynamo_router)

# ─── Catch-all route ─────────────────────────────────────────────────

@app.api_route("/", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def catch_all(request: Request, path: str = ""):
    """
    Catch-all route that detects which AWS service the game client
    is trying to reach and dispatches accordingly.
    """
    host = request.headers.get("host", "")
    target = request.headers.get("x-amz-target", "")
    auth = request.headers.get("authorization", "")
    method = request.method

    print(f"\n{'='*60}")
    print(f"{method} /{path}")
    print(f"Host: {host}")

    # ── 1. Photon Auth: GET / with query string ──
    if method == "GET" and path == "" and str(request.query_params):
        q = request.query_params
        account_id = q.get("UserId") or q.get("userId") or q.get("accountID") or "o_0"
        username = q.get("UserName") or q.get("userName") or q.get("username")
        if not username and account_id:
            account_doc = await accounts.find_one({"accountID": account_id}, {"_id": 0, "displayName": 1})
            if account_doc and isinstance(account_doc.get("displayName"), str) and account_doc["displayName"].strip():
                username = account_doc["displayName"].strip()
        if not username:
            username = GRADIENT_DISPLAY_NAME
        payload = {"ResultCode": 1, "UserId": f"{account_id}$VR${username}"}
        print(f"Service: Photon Auth -> {payload}")
        print(f"{'='*60}\n")
        return JSONResponse(content=payload)

    # Parse body for POST/PUT requests
    raw = await request.body()
    raw_text = _safe_decode(raw)

    # Replay exact responses captured in server.log when possible.
    replay = lookup_replay(method, f"/{path}" if path else "/", raw_text)
    if replay is not None:
        print("Service: Replay | source: server.log")
        print(f"-> {replay['status_code']} {replay['content_type']}")
        print(f"{'='*60}\n")
        return Response(
            content=replay["response_body"],
            status_code=replay["status_code"],
            media_type=replay["content_type"],
        )

    try:
        body = json.loads(raw) if raw else {}
    except Exception:
        body = {}

    # ── 2. Lambda: path matches invocation pattern ──
    m = re.match(r"^2015-03-31/functions/([^/]+)/invocations/?$", path)
    if m or "/lambda/" in auth or host.startswith("lambda"):
        fn = m.group(1) if m else (path or "unknown")
        print(f"Service: Lambda | function: {fn}")
        # Forward to the lambda router handler directly
        from routers.lambda_router import lambda_invoke
        return await lambda_invoke(fn, request)

    # ── 3. DynamoDB: X-Amz-Target header present ──
    if (target and target.startswith("DynamoDB_")) or "/dynamodb/" in auth or host.startswith("dynamodb"):
        op = target.rsplit(".", 1)[-1] if "." in target else "?"
        tbl = body.get("TableName", "")
        if not tbl and isinstance(body, dict):
            ri = body.get("RequestItems", {})
            if isinstance(ri, dict) and ri:
                tbl = ",".join(ri.keys())
        print(f"Service: DynamoDB | op: {op} | table: {tbl}")

        from services.dynamo_ops import dispatch_dynamo
        payload_text, headers = await dispatch_dynamo(target, body)
        print(f"-> 200 application/x-amz-json-1.0")
        print(f"{'='*60}\n")
        return Response(
            content=payload_text,
            media_type="application/x-amz-json-1.0",
            headers=headers,
        )

    # ── 4. Direct API: path matches known handler ──
    # This handles legacy direct endpoints like /questLogIntoAccount
    from routers.lambda_router import HANDLER_TABLE
    fn_lower = path.lower()
    for match_str, handler in HANDLER_TABLE:
        if match_str in fn_lower:
            print(f"Service: Direct API | route: {path} | handler: {handler.__name__}")
            result = await handler(body)
            # Ensure "data" wrapper exists
            if isinstance(result, dict) and "data" not in result:
                result = {"data": result}
            print(f"-> 200 application/json")
            print(f"{'='*60}\n")
            return JSONResponse(content=result)

    # ── 5. Unknown — return empty JSON ──
    print(f"Service: (unknown) - returning {{}}")
    print(f"{'='*60}\n")
    return JSONResponse(content={})


# ─── Entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    ssl_kwargs = {}
    scheme = "http"
    if USE_SSL:
        missing = [str(p) for p in (CERT_FILE, KEY_FILE) if not p.is_file()]
        if missing:
            raise SystemExit(
                f"USE_SSL=1 but missing: {', '.join(missing)}\n"
                f"Run:  python make_cert.py"
            )
        ssl_kwargs = {"ssl_certfile": str(CERT_FILE), "ssl_keyfile": str(KEY_FILE)}
        scheme = "https"

    print(f"Yeeps API listening on {scheme}://{SERVER_HOST}:{SERVER_PORT}")

    uvicorn.run("main:app", host=SERVER_HOST, port=SERVER_PORT, reload=RELOAD, **ssl_kwargs)
