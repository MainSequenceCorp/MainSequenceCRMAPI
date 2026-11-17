"""Explicit Base migration entrypoint. Platform invocation requires user-approved release."""

from metatables import upgrade_application


def main():
    return upgrade_application("src.erp.base.migrations:migration")


if __name__ == "__main__":
    main()
