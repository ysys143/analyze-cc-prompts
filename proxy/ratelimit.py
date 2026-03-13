"""
Rate limit checker via claude -p + local proxy.

Starts a mini proxy on port 8083, runs claude -p with haiku model,
captures anthropic-ratelimit-unified-* headers, prints a summary table.

Usage:
    uv run python ratelimit.py
    uv run python ratelimit.py "custom prompt"
"""

import asyncio
import json
import os
import random
import re
import sys
from datetime import datetime, timezone

import aiohttp
from aiohttp import web

UPSTREAM = "https://api.anthropic.com"
PORT = 8083
MODEL = "claude-haiku-4-5-20251001"

captured_headers: dict[str, str] = {}
captured_usage: dict[str, int] = {}

QUESTIONS = [
    "2+2", "7*8", "12^2", "sqrt(144)", "log2(1024)",
    "capital of France", "capital of Japan", "capital of Brazil",
    "atomic number of gold", "atomic number of carbon",
    "100F in Celsius", "0C in Fahrenheit", "1 mile in km",
    "1 kg in pounds", "1 inch in cm",
    "reverse of 'hello'", "len('anthropic')", "3rd letter of 'python'",
    "is 97 prime", "is 100 prime",
    "largest planet in solar system", "closest planet to sun",
    "speed of light in m/s", "gravitational constant G value",
    "year Python was created", "year C was created",
    "RGB hex for pure red", "RGB hex for pure blue",
    "HTTP status code for not found", "HTTP status code for ok",
    "md5 of empty string (hex)", "sha1 length in bits",
    "binary of 42", "hex of 255",
    "number of days in a leap year", "number of weeks in a year",
    "floor(-2.3)", "ceil(2.1)",
    "sin(0)", "cos(0)", "tan(45 degrees)",
    "e rounded to 3 decimals", "pi rounded to 3 decimals",
    "Fibonacci 10th number", "factorial of 5",
    "GCD of 48 and 18", "LCM of 4 and 6",
    "max of [3,1,4,1,5,9,2,6]", "sum of 1 to 10",
    "boolean: 'True and False'", "boolean: 'not True'",
]


def fmt_reset(value: str) -> str:
    """Format a unix timestamp or ISO string into a compact human-readable form."""
    try:
        ts = int(value)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    except ValueError:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value

    now = datetime.now(tz=timezone.utc)
    delta = dt - now
    secs = delta.total_seconds()

    if secs <= 0:
        return "now"
    elif secs < 86400:
        return dt.strftime("%H:%MZ")
    elif secs < 7 * 86400:
        return dt.strftime("%d %b %H:%MZ")
    else:
        return dt.strftime("%d %b")


async def handle_messages(request: web.Request) -> web.StreamResponse:
    global captured_headers
    body = await request.read()
    try:
        req_json = json.loads(body)
    except json.JSONDecodeError:
        req_json = {}

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
            for k, v in upstream_resp.headers.items():
                if "ratelimit-unified" in k.lower():
                    captured_headers[k.lower()] = v

            if is_stream:
                if upstream_resp.status >= 400:
                    err_body = await upstream_resp.read()
                    return web.Response(status=upstream_resp.status, body=err_body)
                resp = web.StreamResponse(
                    status=upstream_resp.status,
                    headers={
                        k: v for k, v in upstream_resp.headers.items()
                        if k.lower() in ("content-type", "cache-control", "x-request-id", "request-id")
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
                if not client_gone:
                    try:
                        await resp.write_eof()
                    except (ConnectionResetError, ConnectionAbortedError,
                            aiohttp.ClientConnectionError):
                        pass

                # Parse SSE for token usage
                raw = b"".join(chunks).decode("utf-8", errors="replace")
                for line in raw.split("\n"):
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "message_start":
                        usage = event.get("message", {}).get("usage", {})
                        captured_usage["input_tokens"] = usage.get("input_tokens", 0)
                        captured_usage["cache_read"] = usage.get("cache_read_input_tokens", 0)
                        captured_usage["cache_write"] = usage.get("cache_creation_input_tokens", 0)
                    elif event.get("type") == "message_delta":
                        captured_usage["output_tokens"] = event.get("usage", {}).get("output_tokens", 0)

                return resp
            else:
                resp_body = await upstream_resp.read()
                return web.Response(
                    status=upstream_resp.status,
                    headers={
                        k: v for k, v in upstream_resp.headers.items()
                        if k.lower() in ("content-type", "x-request-id", "request-id")
                    },
                    body=resp_body,
                )


async def handle_passthrough(request: web.Request) -> web.Response:
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
                headers={k: v for k, v in upstream_resp.headers.items() if k.lower() == "content-type"},
                body=resp_body,
            )


# Matches time-window bucket names like 5h, 7d, 7d_sonnet, 30d_haiku
BUCKET_RE = re.compile(r"^\d+[hd](_\w+)?$")


def parse_rate_limits(headers: dict[str, str]) -> dict:
    prefix = "anthropic-ratelimit-unified-"
    rep_claim = headers.get(f"{prefix}representative-claim", "")
    overage_status = headers.get(f"{prefix}overage-status", "")
    overage_disabled_reason = headers.get(f"{prefix}overage-disabled-reason", "")
    fallback = headers.get(f"{prefix}fallback", "")
    fallback_pct = headers.get(f"{prefix}fallback-percentage", "")

    buckets: dict[str, dict[str, str]] = {}
    skip = {
        "representative-claim", "overage-status", "overage-disabled-reason",
        "fallback", "fallback-percentage", "status", "reset",
    }

    for k, v in headers.items():
        if not k.startswith(prefix):
            continue
        remainder = k[len(prefix):]
        if remainder in skip:
            continue
        parts = remainder.rsplit("-", 1)
        if len(parts) != 2:
            continue
        bucket, field = parts
        if not BUCKET_RE.match(bucket):
            continue
        buckets.setdefault(bucket, {})[field] = v

    return {
        "rep_claim": rep_claim,
        "overage_status": overage_status,
        "overage_disabled_reason": overage_disabled_reason,
        "fallback": fallback,
        "fallback_pct": fallback_pct,
        "buckets": buckets,
    }


def print_rate_limits(headers: dict[str, str]) -> None:
    if not headers:
        print("No rate limit headers captured.")
        return

    data = parse_rate_limits(headers)
    buckets = data["buckets"]
    rep_claim = data["rep_claim"]
    overage_status = data["overage_status"]
    overage_disabled_reason = data["overage_disabled_reason"]
    fallback = data["fallback"]
    fallback_pct = data["fallback_pct"]

    width = 65
    lines = []
    lines.append(f"┌─ Anthropic Unified Rate Limit {'─' * (width - 31)}┐")

    if rep_claim:
        lines.append(f"│ representative-claim : {rep_claim:<{width - 25}}│")
    lines.append(f"│{' ' * width}│")

    for bucket in sorted(buckets):
        fields = buckets[bucket]
        status = fields.get("status", "—")
        util = fields.get("utilization", "—")
        reset_raw = fields.get("reset", "—")
        reset = fmt_reset(reset_raw) if reset_raw != "—" else "—"

        # utilization: already a percentage string like "54%" or a decimal
        if util not in ("—", "?") and not util.endswith("%"):
            try:
                util = f"{float(util):.0%}"
            except ValueError:
                pass

        row = f" {bucket:<8} │ {status:<9} │ util: {util:<6} │ reset: {reset}"
        lines.append(f"│{row:<{width}}│")

    lines.append(f"│{' ' * width}│")

    # Overage line
    if overage_status == "rejected" and overage_disabled_reason:
        overage_line = f" overage: rejected ({overage_disabled_reason})"
    elif overage_status:
        overage_line = f" overage: {overage_status}"
    else:
        overage_line = " overage: —"
    lines.append(f"│{overage_line:<{width}}│")

    # Fallback line (if present)
    if fallback or fallback_pct:
        fb_line = f" fallback: {fallback or '—'}"
        if fallback_pct:
            fb_line += f"  ({fallback_pct}%)"
        lines.append(f"│{fb_line:<{width}}│")

    lines.append(f"└{'─' * width}┘")
    print("\n".join(lines))


async def run(prompt: str) -> None:
    app = web.Application()
    app.router.add_post("/v1/messages", handle_messages)
    app.router.add_route("*", "/{path:.*}", handle_passthrough)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    env = {**os.environ, "ANTHROPIC_BASE_URL": f"http://localhost:{PORT}"}
    # Mirror what the `claude` shell function does: unset conflicting auth/model vars
    for key in ("CLAUDECODE", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"):
        env.pop(key, None)
    env["CLAUDE_CONFIG_DIR"] = os.path.expanduser("~/.claude-2")

    # Use the real binary directly — the `claude` shell function strips ANTHROPIC_BASE_URL
    claude_bin = os.path.expanduser("~/.nvm/versions/node/v20.18.1/bin/claude")
    proc = await asyncio.create_subprocess_exec(
        claude_bin, "-p", prompt, "--model", MODEL,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if stdout:
        print(stdout.decode("utf-8", errors="replace"), end="")

    await runner.cleanup()
    print()
    if captured_usage:
        inp = captured_usage.get("input_tokens", 0)
        out = captured_usage.get("output_tokens", 0)
        cr = captured_usage.get("cache_read", 0)
        cw = captured_usage.get("cache_write", 0)
        parts = [f"input: {inp}", f"output: {out}"]
        if cr:
            parts.append(f"cache_read: {cr}")
        if cw:
            parts.append(f"cache_write: {cw}")
        print(f"tokens — {',  '.join(parts)}")
    print_rate_limits(captured_headers)


def main() -> None:
    prompt = sys.argv[1] if len(sys.argv) > 1 else f"answer in one word or number only: {random.choice(QUESTIONS)}"
    asyncio.run(run(prompt))


if __name__ == "__main__":
    main()
