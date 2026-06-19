# network.py — Network utility with optional proxy support
#
# Provides NetworkError + ensure_network() + fetch_with_retry.
# All network I/O modules use check_proxy / ensure_network / fetch_with_retry.
#
# Proxy is OPTIONAL. Set BIOMED_PROXY_HOST / BIOMED_PROXY_PORT env vars
# if your environment requires a proxy (e.g., GFW). If not set, network
# calls go direct — no proxy check, no hard failure.

from __future__ import annotations

import logging
import os
import socket
import ssl
import time
from typing import Optional
from urllib import request as urllib_request
from urllib.error import URLError

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Proxy configuration (optional — only used when env vars are set)
# ═══════════════════════════════════════════════════════════════

_PROXY_HOST = os.environ.get("BIOMED_PROXY_HOST", "")
_PROXY_PORT = int(os.environ.get("BIOMED_PROXY_PORT", "0"))


def is_proxy_configured() -> bool:
    """Return True if a proxy host/port has been explicitly configured."""
    return bool(_PROXY_HOST) and _PROXY_PORT > 0


# ═══════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════


class NetworkError(Exception):
    """Network is unreachable (proxy configured but down, or direct connection failed)."""
    pass


class RetryExhaustedError(NetworkError):
    """All retry attempts exhausted."""
    pass


# ═══════════════════════════════════════════════════════════════
# Proxy check
# ═══════════════════════════════════════════════════════════════


def check_proxy(
    host: str | None = None,
    port: int | None = None,
    timeout: float = 2.0,
) -> bool:
    """Check whether the configured proxy is reachable.

    If no proxy is configured, returns True immediately (nothing to check).

    Args:
        host: Proxy host. Defaults to BIOMED_PROXY_HOST env var.
        port: Proxy port. Defaults to BIOMED_PROXY_PORT env var.
        timeout: Connection timeout in seconds.

    Returns:
        True if proxy is reachable or no proxy is configured.
        False if proxy is configured but unreachable.
    """
    if host is None:
        host = _PROXY_HOST
    if port is None:
        port = _PROXY_PORT

    if not host or port <= 0:
        return True  # No proxy configured → nothing to check

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def ensure_network() -> None:
    """Verify network is available before making external calls.

    If a proxy is configured (BIOMED_PROXY_HOST / BIOMED_PROXY_PORT),
    checks that it is reachable. If not configured, passes through —
    actual network calls will succeed or fail on their own merits.

    Raises:
        NetworkError: Proxy is configured but unreachable.
    """
    if not is_proxy_configured():
        return  # No proxy → let actual network calls handle their own fate

    if not check_proxy():
        raise NetworkError(
            f"Proxy ({_PROXY_HOST}:{_PROXY_PORT}) is configured but unreachable. "
            "Start your proxy or unset BIOMED_PROXY_HOST / BIOMED_PROXY_PORT "
            "to use direct connections."
        )


# ═══════════════════════════════════════════════════════════════
# HTTP request with retry
# ═══════════════════════════════════════════════════════════════


def fetch_with_retry(
    url: str,
    max_retries: int = 3,
    base_timeout: int = 30,
    headers: Optional[dict[str, str]] = None,
) -> str:
    """HTTP GET with exponential-backoff retry.

    Implements RULE-API-006 retry pattern:
    - 3 attempts total
    - Exponential backoff: sleep(2 ** attempt)
    - Increasing timeout: timeout = base_timeout * (attempt + 1)

    Args:
        url: Request URL.
        max_retries: Maximum attempts (including the first).
        base_timeout: Base timeout in seconds.
        headers: Optional HTTP headers dict.

    Returns:
        Response body as text.

    Raises:
        NetworkError: Proxy is configured but down.
        RetryExhaustedError: All retries failed.
    """
    # Only checks proxy if one is configured; passes through otherwise
    ensure_network()

    # Windows + GFW: SSL revocation check can hang. Use unverified context.
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        timeout = base_timeout * (attempt + 1)
        try:
            req = urllib_request.Request(url)
            if headers:
                for key, value in headers.items():
                    req.add_header(key, value)
            with urllib_request.urlopen(req, timeout=timeout, context=ssl_ctx) as resp:
                return resp.read().decode("utf-8")
        except (URLError, OSError, TimeoutError) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    "HTTP request failed (attempt %d/%d, retrying in %ds): %s "
                    "| URL: %s",
                    attempt + 1,
                    max_retries,
                    wait,
                    e,
                    url[:120],
                )
                time.sleep(wait)

    raise RetryExhaustedError(
        f"All {max_retries} attempts failed for URL: {url[:200]}. "
        f"Last error: {last_error}"
    )
