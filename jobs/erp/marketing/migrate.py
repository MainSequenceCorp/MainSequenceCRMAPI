"""Marketing-only migration job; scheduled only in an approved release workflow."""

from metatables import upgrade_application


def main():
    upgrade_application("src.erp.marketing.migrations:migration")


if __name__ == "__main__":
    main()
