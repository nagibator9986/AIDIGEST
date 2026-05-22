"""Liveness heartbeat.

The running process touches :data:`HEARTBEAT_PATH` on every delivery tick
(once a minute). Executed as a module (``python -m app.health``) it instead
*checks* that heartbeat — this is what the Docker ``HEALTHCHECK`` runs.
"""

from __future__ import annotations

import contextlib
import sys
import tempfile
import time
from pathlib import Path

HEARTBEAT_PATH = Path(tempfile.gettempdir()) / "aidigest.heartbeat"
# Delivery ticks every 60 s; allow three missed ticks before "unhealthy".
MAX_STALE_SECONDS = 200


def touch() -> None:
    """Record a liveness heartbeat (best effort — never raises)."""
    with contextlib.suppress(OSError):
        HEARTBEAT_PATH.write_text(str(time.time()), encoding="utf-8")


def is_healthy() -> bool:
    """True if the heartbeat exists and is fresh."""
    try:
        age = time.time() - HEARTBEAT_PATH.stat().st_mtime
    except OSError:
        return False
    return age <= MAX_STALE_SECONDS


def main() -> int:
    """Entry point for the container healthcheck."""
    if is_healthy():
        return 0
    print("unhealthy: heartbeat missing or stale", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
