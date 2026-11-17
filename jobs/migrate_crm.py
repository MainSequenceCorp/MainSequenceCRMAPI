"""Compatibility launcher for the CRM migration Job."""

import runpy

if __name__ == "__main__":
    runpy.run_module("jobs.erp.crm.migrate", run_name="__main__")
