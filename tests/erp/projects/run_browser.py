"""Run the companion browser suite with owned verified-local fixtures."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from tests.erp.finance.conftest import business as finance_business
from tests.erp.finance.conftest import finance_services
from tests.erp.projects.conftest import business, project_services
from tests.erp.sales.conftest import business as sales_business
from tests.erp.sales.conftest import services as sales_services


def finish(generator):
    try:
        next(generator)
    except StopIteration:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", type=Path, required=True)
    args = parser.parse_args()
    fixture = business.__wrapped__(project_services.__wrapped__())
    data = next(fixture)
    sales_fixture = sales_business.__wrapped__(sales_services.__wrapped__())
    sales = next(sales_fixture)
    finance_fixture = finance_business.__wrapped__(finance_services.__wrapped__())
    finance = next(finance_fixture)
    with TemporaryDirectory(prefix="projects-browser-") as directory:
        source, owned = Path(directory) / "fixture.json", Path(directory) / "owned.json"
        owned.write_text("[]")
        try:
            order = sales["new"]()
            order = sales["sales"].transition(order["uid"], "confirm", 1)
            source.write_text(
                json.dumps(
                    {
                        "payload": data["payload"],
                        "party_name": data["party"]["name"],
                        "company_name": data["company"]["name"],
                        "person_name": data["person"]["name"],
                        "order": order,
                    },
                    default=str,
                )
            )
            subprocess.run(
                ["node", "tests/erp/projects/browser/projects.browser.mjs"],
                cwd=args.frontend,
                env={
                    **os.environ,
                    "PROJECTS_BROWSER_FIXTURE": str(source),
                    "PROJECTS_BROWSER_OWNED": str(owned),
                },
                check=True,
            )
        finally:
            for resource, uid in json.loads(owned.read_text()):
                if resource == "projects":
                    data["projects"].append(UUID(uid))
                else:
                    finance["documents"].append(("invoices", UUID(uid)))
            try:
                finish(fixture)
            finally:
                try:
                    finish(finance_fixture)
                finally:
                    finish(sales_fixture)


if __name__ == "__main__":
    main()
