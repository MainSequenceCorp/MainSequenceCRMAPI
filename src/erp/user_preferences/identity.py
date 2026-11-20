"""Resolve the verified person used for ERP settings and connector admission."""

from mainsequence.client import OrganizationEnvironment, User
from mainsequence.server.fastapi import reads_as_caller

from .errors import UserPreferencesError


def is_local_person(profile):
    # Older local platform profiles omit the type. Only a verified active
    # Organization administrator qualifies for that local compatibility path.
    return profile.is_active is True and (
        profile.identity_type == "human"
        or (profile.identity_type is None and profile.is_organization_admin is True)
    )


def active_hosted_person(uid):
    uid = str(uid)
    with reads_as_caller():
        profile = User.get_by_uid(uid)
        if str(profile.uid) != uid or profile.is_active is not True:
            return None
        if profile.identity_type == "human":
            return profile
        if profile.identity_type is not None:
            return None
        # Some human directory projections omit the type. Require an exact
        # human-filtered match instead of treating the missing field as human.
        matches = User.filter(uid=uid, identity_type="human")
    if len(matches) != 1:
        return None
    person = matches[0]
    if (
        str(person.uid) == uid
        and person.is_active is True
        and person.identity_type in (None, "human")
    ):
        return profile
    return None


def request_person(*, local):
    requester = User.get_requester()
    if requester is not None:
        return requester
    caller = User.get_logged_user()
    if local:
        # The local launcher only supplies the real signed-in CLI identity.
        profile = User.get_authenticated_user_details()
        if str(profile.uid) != str(caller.uid):
            raise UserPreferencesError(403, "forbidden", "The local SDK identity changed")
        if not is_local_person(profile):
            raise UserPreferencesError(403, "person_required", "User Preferences requires a person")
        return profile
    if active_hosted_person(caller.uid) is None:
        raise UserPreferencesError(403, "person_required", "User Preferences requires a person")
    return caller


def require_workflow_admin(binding, person):
    """Apply the binding's administrator gate after verifying caller identity."""
    if binding.admin_only and getattr(person(), "is_organization_admin", False) is not True:
        raise UserPreferencesError(403, "integration_admin_required", "ERP administrator access is required")


def connector_request_person(actor_uid, scope, *, local):
    """Resolve the actor already verified by an approved connector workload."""
    if local:
        person = request_person(local=True)
        return person if str(person.uid) == str(actor_uid) else None
    person = active_hosted_person(actor_uid)
    if person and str(getattr(person.organization, "uid", None)) == str(
        OrganizationEnvironment.get_by_uid(str(scope)).organization_owner_uid
    ):
        return person
    return None
