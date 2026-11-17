"""Owned Marketing local fixtures and an existing CRM follow-up for actual browser reads."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from tests.erp.marketing.conftest import mailings, marketing_services
from tests.erp.marketing.crm_fixture import crm_followup_fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", type=Path, required=True)
    args = parser.parse_args()
    gen = mailings.__wrapped__(marketing_services.__wrapped__())
    f = next(gen)
    with TemporaryDirectory(prefix="marketing-browser-") as directory:
        fixture = Path(directory) / "fixture.json"
        owned = Path(directory) / "owned.json"
        owned.write_text("[]")
        try:
            person = f["person"]()
            with crm_followup_fixture(f["service"], person) as task:
                fixture.write_text(json.dumps({"person": person, "task": task}, default=str))
                subprocess.run(
                    ["node", "tests/erp/marketing/browser/marketing.browser.mjs"],
                    cwd=args.frontend,
                    env={
                        **os.environ,
                        "MARKETING_BROWSER_FIXTURE": str(fixture),
                        "MARKETING_BROWSER_OWNED": str(owned),
                    },
                    check=True,
                )
        finally:
            for kind, uid in json.loads(owned.read_text()):
                f[kind].append(UUID(uid))
            try:
                next(gen)
            except StopIteration:
                pass


if __name__ == "__main__":
    main()
