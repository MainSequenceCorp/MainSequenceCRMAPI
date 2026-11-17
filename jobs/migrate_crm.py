"""Compatibility launcher for the CRM migration Job."""

import runpy
from pathlib import Path


def main() -> None:
    implementation = Path(__file__).resolve().parent / "erp" / "crm" / "migrate.py"
    runpy.run_path(str(implementation), run_name="__main__")


if __name__ == "__main__":
    main()
