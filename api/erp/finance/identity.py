"""Finance policy uses verified platform identities and Teams, never CRM permissions."""

import os
from uuid import UUID

from mainsequence.client import User

ALL_CAPABILITIES = frozenset({"finance.read", "finance.write", "finance.post", "finance.configure"})


def actor_and_capabilities(*, local=False):
    identity = User.get_requester() or User.get_logged_user()
    actor = UUID(str(identity.uid))
    if local or identity.is_organization_admin:
        return actor, ALL_CAPABILITIES
    groups = {}
    for role in ("reader", "writer", "poster", "admin"):
        groups[role] = {
            str(UUID(value.strip()))
            for value in os.environ.get(f"FINANCE_{role.upper()}_TEAM_UIDS", "").split(",")
            if value.strip()
        }
    memberships = identity.in_teams(set().union(*groups.values()), max_age_seconds=0)
    if memberships & groups["admin"]:
        return actor, ALL_CAPABILITIES
    if memberships & groups["poster"]:
        return actor, {"finance.read", "finance.write", "finance.post"}
    if memberships & groups["writer"]:
        return actor, {"finance.read", "finance.write"}
    if memberships & groups["reader"]:
        return actor, {"finance.read"}
    return actor, set()
