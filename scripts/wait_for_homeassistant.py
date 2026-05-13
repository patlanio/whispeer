from __future__ import annotations

import argparse
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


READY_LOG_MARKERS = (
    "Home Assistant initialized",
    "Setup complete",
)


def _http_ready(base_url: str) -> bool:
    request = Request(base_url, headers={"User-Agent": "whispeer-makefile"})
    try:
        with urlopen(request, timeout=5) as response:
            return response.status < 500
    except HTTPError as exc:
        return exc.code < 500
    except (ConnectionResetError, TimeoutError, URLError, socket.timeout, OSError):
        return False


def _logs_ready(container_name: str | None) -> bool:
    if not container_name:
        return False
    result = subprocess.run(
        ["docker", "logs", container_name],
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"
    return any(marker in output for marker in READY_LOG_MARKERS)


def wait_for_homeassistant(base_url: str, container_name: str | None, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    successful_checks = 0

    while time.monotonic() < deadline:
        if _http_ready(base_url):
            successful_checks += 1
            if successful_checks >= 3 or _logs_ready(container_name):
                return
        else:
            successful_checks = 0
        time.sleep(2)

    raise TimeoutError(f"Timed out waiting for Home Assistant at {base_url}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait until a Home Assistant instance is reachable.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--container-name")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    wait_for_homeassistant(args.base_url.rstrip("/"), args.container_name, args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
