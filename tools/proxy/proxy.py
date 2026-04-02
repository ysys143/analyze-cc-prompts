"""
Transparent reverse proxy for Claude Code API message capture.

Intercepts requests to the Anthropic Messages API, logs request/response
payloads to disk, and forwards everything transparently.

Usage:
    uv run python proxy.py

    # In another terminal:
    ANTHROPIC_BASE_URL=http://localhost:8082 claude

Environment variables:
    PROXY_UPSTREAM   Upstream API URL (default: https://api.anthropic.com)
    PROXY_PORT       Listen port (default: 8082)
    PROXY_DUMPS_DIR  Directory for request/response dumps (default: ./dumps)
"""

import json
import os
from datetime import datetime, timezone

import aiohttp
from aiohttp import web

UPSTREAM = os.environ.get("PROXY_UPSTREAM", "https://api.anthropic.com")
PORT = int(os.environ.get("PROXY_PORT", "8082"))
DUMPS_DIR = os.environ.get("PROXY_DUMPS_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "dumps"))


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S.%f")[:-3]


def dump_json(name: str, data: object) -> str:
    path = os.path.join(DUMPS_DIR, name)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


async def handle_messages(request: web.Request) -> web.StreamResponse:
    """Handle POST /v1/messages — log, forward, stream back, log response."""
    ts = timestamp()
    body = await request.read()

    # Dump request
    try:
        req_json = json.loads(body)
    except json.JSONDecodeError:
        req_json = {"_raw": body.decode("utf-8", errors="replace")}
    req_path = dump_json(f"{ts}-req.json", req_json)
    print(f"[{ts}] REQ  → {req_path}")

    # Build upstream headers (forward everything except Host)
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "transfer-encoding")
    }

    is_stream = req_json.get("stream", False)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{UPSTREAM}{request.path}",
            headers=headers,
            data=body,
        ) as upstream_resp:

            # Log rate-limit / usage headers for quick visibility
            limit_headers = {
                k: v for k, v in upstream_resp.headers.items()
                if any(kw in k.lower() for kw in ("ratelimit", "rate-limit", "limit", "usage", "retry"))
            }
            if limit_headers:
                pairs = ", ".join(f"{k}={v}" for k, v in limit_headers.items())
                print(f"[{ts}] LIMITS: {pairs}")

            if is_stream:
                # SSE streaming: forward chunks in real-time, accumulate for dump
                resp = web.StreamResponse(
                    status=upstream_resp.status,
                    headers={
                        k: v for k, v in upstream_resp.headers.items()
                        if k.lower() in (
                            "content-type", "cache-control",
                            "x-request-id", "request-id",
                        )
                    },
                )
                await resp.prepare(request)

                chunks = []
                client_gone = False
                async for chunk in upstream_resp.content.iter_any():
                    chunks.append(chunk)
                    if not client_gone:
                        try:
                            await resp.write(chunk)
                        except (ConnectionResetError, ConnectionAbortedError,
                                aiohttp.ClientConnectionError):
                            client_gone = True
                            print(f"[{ts}] WARN client disconnected, still capturing response")

                if not client_gone:
                    try:
                        await resp.write_eof()
                    except (ConnectionResetError, ConnectionAbortedError,
                            aiohttp.ClientConnectionError):
                        pass

                # Parse accumulated SSE events for the dump
                raw = b"".join(chunks).decode("utf-8", errors="replace")
                events = []
                for line in raw.split("\n"):
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            events.append("[DONE]")
                        else:
                            try:
                                events.append(json.loads(data_str))
                            except json.JSONDecodeError:
                                events.append(data_str)

                res_path = dump_json(f"{ts}-res.json", {
                    "status": upstream_resp.status,
                    "headers": dict(upstream_resp.headers),
                    "events": events,
                })
                print(f"[{ts}] RES  ← {res_path} (streamed, {len(events)} events)")
                return resp

            else:
                # Non-streaming: read full response, dump, return
                resp_body = await upstream_resp.read()
                try:
                    res_json = json.loads(resp_body)
                except json.JSONDecodeError:
                    res_json = {"_raw": resp_body.decode("utf-8", errors="replace")}

                res_path = dump_json(f"{ts}-res.json", {
                    "status": upstream_resp.status,
                    "headers": dict(upstream_resp.headers),
                    "body": res_json,
                })
                print(f"[{ts}] RES  ← {res_path}")

                return web.Response(
                    status=upstream_resp.status,
                    headers={
                        k: v for k, v in upstream_resp.headers.items()
                        if k.lower() in ("content-type", "x-request-id", "request-id")
                    },
                    body=resp_body,
                )


async def handle_passthrough(request: web.Request) -> web.Response:
    """Forward any non-messages endpoint transparently."""
    body = await request.read()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "transfer-encoding")
    }

    async with aiohttp.ClientSession() as session:
        async with session.request(
            request.method,
            f"{UPSTREAM}{request.path}",
            headers=headers,
            data=body if body else None,
        ) as upstream_resp:
            resp_body = await upstream_resp.read()
            return web.Response(
                status=upstream_resp.status,
                headers={
                    k: v for k, v in upstream_resp.headers.items()
                    if k.lower() == "content-type"
                },
                body=resp_body,
            )


def main():
    os.makedirs(DUMPS_DIR, exist_ok=True)

    app = web.Application()
    app.router.add_post("/v1/messages", handle_messages)
    # Catch-all for other endpoints
    app.router.add_route("*", "/{path:.*}", handle_passthrough)

    print(f"Proxy listening on http://localhost:{PORT}")
    print(f"Dumps directory: {DUMPS_DIR}")
    print(f"Upstream: {UPSTREAM}")
    print()
    print(f"Usage: ANTHROPIC_BASE_URL=http://localhost:{PORT} claude")
    web.run_app(app, host="0.0.0.0", port=PORT, print=None)


if __name__ == "__main__":
    main()
