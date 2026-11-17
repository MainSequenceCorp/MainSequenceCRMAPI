"""Compatibility launcher for the CRM migration Job."""

def main() -> None:
    from jobs.erp.crm.migrate import main as migrate

    migrate()

if __name__ == "__main__":
    main()
