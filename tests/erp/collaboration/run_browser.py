"""Owned actual MetaTables Local fixtures for the companion browser suite."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from tests.erp.collaboration.conftest import collaboration_service, discussions
from tests.erp.projects.conftest import business, project_services


def finish(gen):
    try:
        next(gen)
    except StopIteration:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", type=Path, required=True)
    args = parser.parse_args()
    gen = discussions.__wrapped__(collaboration_service.__wrapped__())
    f = next(gen)
    pgen = business.__wrapped__(project_services.__wrapped__())
    p = next(pgen)
    with TemporaryDirectory(prefix="collaboration-browser-") as directory:
        fixture = Path(directory) / "fixture.json"
        owned = Path(directory) / "owned.json"
        owned.write_text("[]")
        try:
            project = p["new"]()
            fixture.write_text(json.dumps({"project": project}, default=str))
            subprocess.run(
                ["node", "tests/erp/collaboration/browser/collaboration.browser.mjs"],
                cwd=args.frontend,
                env={
                    **os.environ,
                    "COLLABORATION_BROWSER_FIXTURE": str(fixture),
                    "COLLABORATION_BROWSER_OWNED": str(owned),
                },
                check=True,
            )
        finally:
            f["owned"] += [UUID(uid) for uid in json.loads(owned.read_text())]
            try:
                finish(gen)
            finally:
                finish(pgen)


if __name__ == "__main__":
    main()
