"""Finance policy uses verified platform identities and Teams, never CRM permissions."""

import os
from uuid import UUID

from mainsequence.client import User

ALL_CAPABILITIES = frozenset({"finance.read", "finance.write", "finance.post", "finance.configure"})


def finance_role_groups():
    return {
        role: {
            str(UUID(value.strip()))
            for value in os.environ.get(f"FINANCE_{role.upper()}_TEAM_UIDS", "").split(",")
            if value.strip()
        }
        for role in ("reader", "writer", "poster", "admin")
    }


def finance_capabilities(memberships, is_admin, groups):
    if is_admin or memberships & groups["admin"]:
        return ALL_CAPABILITIES
    if memberships & groups["poster"]:
        return {"finance.read", "finance.write", "finance.post"}
    if memberships & groups["writer"]:
        return {"finance.read", "finance.write"}
    if memberships & groups["reader"]:
        return {"finance.read"}
    return set()


def actor_and_capabilities(*, local=False):
    identity = User.get_requester() or User.get_logged_user()
    actor = UUID(str(identity.uid))
    if local or identity.is_organization_admin:
        return actor, ALL_CAPABILITIES
    groups = finance_role_groups()
    memberships = identity.in_teams(set().union(*groups.values()), max_age_seconds=0)
    return actor, finance_capabilities(memberships, False, groups)
