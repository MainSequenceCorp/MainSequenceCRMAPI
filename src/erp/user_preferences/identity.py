"""Classify the verified SDK profile used by the loopback launcher."""


def is_local_person(profile):
    # Older local platform profiles omit the type. Only a verified active
    # Organization administrator qualifies for that local compatibility path.
    return profile.is_active is True and (
        profile.identity_type == "human"
        or (profile.identity_type is None and profile.is_organization_admin is True)
    )
