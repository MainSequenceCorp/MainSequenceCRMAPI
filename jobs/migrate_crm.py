"""Compatibility launcher for the CRM migration Job."""

import runpy


def main() -> None:
    runpy.run_module("jobs.erp.crm.migrate", run_name="__main__")


if __name__ == "__main__":
    main()
