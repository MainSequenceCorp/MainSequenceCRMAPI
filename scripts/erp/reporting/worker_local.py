"""Advance bounded private report refresh work through the authenticated loopback API."""

import argparse
import time

import httpx

from metatables import configure_local_client
from src.erp.reporting.store import require_local_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-uid", required=True)
    parser.add_argument("--port", type=int, default=38771)
    parser.add_argument("--poll-seconds", type=int, default=5, choices=range(1, 16))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    configure_local_client()
    if str(require_local_runtime()) != args.source_uid:
        raise RuntimeError("Unexpected local source; worker stopped")
    previous = None
    while True:
        if str(require_local_runtime()) != args.source_uid:
            raise RuntimeError("Local source changed; worker stopped")
        try:
            # Launcher verifies its SDK sign-in. Never forward caller/actor headers.
            response = httpx.post(
                f"http://127.0.0.1:{args.port}/api/reporting/v1/worker/tick/", json={}, timeout=130
            )
            if response.status_code == 200:
                result = response.json()
                status = (result["run_uid"], result["state"])
            else:
                status = (None, "request_failed_" + str(response.status_code))
        except httpx.HTTPError:
            status = (None, "connection_unavailable")
        if status != previous:
            print({"run_uid": status[0], "state": status[1]}, flush=True)
            previous = status
        if args.once:
            return
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
