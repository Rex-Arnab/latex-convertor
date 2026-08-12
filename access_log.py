"""Per-request access logging to a file.

Writes one line per API call to API_LOG_FILE (default ./logs/access.log). Uses
WatchedFileHandler so the file can be rotated externally by logrotate while the
(multiple) uvicorn workers keep appending to the live file. Client IP prefers
Cloudflare's CF-Connecting-IP, since the service sits behind Cloudflare -> nginx.
"""

from __future__ import annotations

import logging
import os
import time
from logging.handlers import WatchedFileHandler

LOG_FILE = os.environ.get(
    "API_LOG_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "access.log"),
)

# Response headers worth recording for /convert calls.
_CONVERT_HEADERS = {
    "x-source-format": "src",
    "x-target-format": "dst",
    "x-engine-used": "engine",
    "x-equations-converted": "eq",
}


def _build_logger() -> logging.Logger:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    log = logging.getLogger("api.access")
    log.setLevel(logging.INFO)
    log.propagate = False
    if not log.handlers:
        handler = WatchedFileHandler(LOG_FILE, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        log.addHandler(handler)
    return log


logger = _build_logger()


def client_ip(request) -> str:
    h = request.headers
    fwd = h.get("x-forwarded-for", "").split(",")[0].strip()
    return (
        h.get("cf-connecting-ip")
        or fwd
        or h.get("x-real-ip")
        or (request.client.host if request.client else "-")
    )


async def log_requests(request, call_next):
    """Starlette HTTP middleware: log method, path, status, duration, client, size."""
    start = time.perf_counter()
    ip = client_ip(request)
    in_bytes = request.headers.get("content-length", "-")
    ua = request.headers.get("user-agent", "-")
    try:
        response = await call_next(request)
    except Exception:
        dur = (time.perf_counter() - start) * 1000
        logger.info(
            '%s "%s %s" 500 %.0fms in=%s ua="%s" ERROR',
            ip,
            request.method,
            request.url.path,
            dur,
            in_bytes,
            ua,
        )
        raise

    dur = (time.perf_counter() - start) * 1000
    extra = ""
    if request.url.path == "/convert":
        bits = []
        # filename stashed on request.state by the upload validator
        fname = (request.scope.get("state") or {}).get("upload_name")
        if fname:
            safe = fname.replace('"', "'").replace("\n", " ").replace("\r", " ")[:200]
            bits.append(f'file="{safe}"')
        bits += [
            f"{label}={response.headers[h]}"
            for h, label in _CONVERT_HEADERS.items()
            if h in response.headers
        ]
        if bits:
            extra = " " + " ".join(bits)
    logger.info(
        '%s "%s %s" %d %.0fms in=%s%s ua="%s"',
        ip,
        request.method,
        request.url.path,
        response.status_code,
        dur,
        in_bytes,
        extra,
        ua,
    )
    return response
