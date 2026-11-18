"""Apply the User Preferences provider in its approved migration Job."""

from metatables import upgrade_application


def main():
    upgrade_application("src.erp.user_preferences.migrations:migration")


if __name__ == "__main__":
    main()
