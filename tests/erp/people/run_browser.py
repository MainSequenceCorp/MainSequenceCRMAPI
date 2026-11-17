"""Owned MetaTables Local fixtures for the real companion People browser suite."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from tests.erp.people.conftest import people_services, workforce
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
    gen = workforce.__wrapped__(people_services.__wrapped__())
    f = next(gen)
    project_gen = business.__wrapped__(project_services.__wrapped__())
    p = next(project_gen)
    with TemporaryDirectory(prefix="people-browser-") as directory:
        fixture = Path(directory) / "fixture.json"
        owned = Path(directory) / "owned.json"
        owned.write_text("[]")
        try:
            project = p["new"](operating_company_uid=f["company"]["uid"])
            task = p["task"](
                project, assignee_party_uid=None, name="People staffing " + uuid4().hex[:10]
            )
            second = f["base_create"]("parties", kind="person")
            other = f["employee"](person_uid=second["uid"])
            # A distinct policy-test actor owns this fixture request. Browser approval
            # itself uses actual SDK authentication, never an injected fake identity.
            svc = f["service"]
            original = svc.actor_uid
            svc.actor_uid = uuid4()
            try:
                row = f["absence"](other)
                row = svc.absence_action(
                    row["uid"],
                    "submit",
                    {
                        "expected_version": row["version"],
                        "expected_employee_version": row["employee_version"],
                        "note": "",
                    },
                )
            finally:
                svc.actor_uid = original
            fixture.write_text(
                json.dumps(
                    {
                        "person": f["person"],
                        "company": f["company"],
                        "task": task,
                        "other_request": row,
                    },
                    default=str,
                )
            )
            subprocess.run(
                ["node", "tests/erp/people/browser/people.browser.mjs"],
                cwd=args.frontend,
                env={
                    **os.environ,
                    "PEOPLE_BROWSER_FIXTURE": str(fixture),
                    "PEOPLE_BROWSER_OWNED": str(owned),
                },
                check=True,
            )
        finally:
            f["records"] += [(kind, UUID(uid)) for kind, uid in json.loads(owned.read_text())]
            try:
                finish(project_gen)
            finally:
                finish(gen)


if __name__ == "__main__":
    main()
