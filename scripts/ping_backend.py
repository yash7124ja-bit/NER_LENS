"""Run outside Render: BACKEND_HEALTH_URL must point to /health/ready."""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def ping(url: str) -> bool:
    try:
        request = Request(url, headers={"User-Agent": "NER-LENS-health-check"})
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read(4096))
            return (
                response.status == 200
                and isinstance(payload, dict)
                and payload.get("status") == "ready"
            )
    except (URLError, OSError, ValueError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="Check once and exit for external schedulers"
    )
    args = parser.parse_args()
    url = os.environ.get("BACKEND_HEALTH_URL", "")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != "/health/ready"
    ):
        parser.error("Set BACKEND_HEALTH_URL to the backend HTTPS /health/ready URL")
    try:
        while True:
            started = time.monotonic()
            healthy = ping(url)
            print(
                f"{datetime.now(timezone.utc).isoformat()} {'ready' if healthy else 'unavailable'}",
                flush=True,
            )
            if args.once:
                return 0 if healthy else 1
            time.sleep(max(0, 600 - (time.monotonic() - started)))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
