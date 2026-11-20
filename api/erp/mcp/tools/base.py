"""Business Directory lookups backed by the Base owner's read operations."""

from typing import Literal

from api.erp.base.main import service_for

from ..contracts import ListInput
from ..owner_routes import OwnerRoutes
from ..registry import register_reads


class PartyListInput(ListInput):
    kind: Literal["person", "organization"] | None = None


def register_tools(registry):
    register_reads(
        registry,
        owner="base",
        skill="base/base-directory",
        service=lambda scope: service_for(scope.apps["base"], local=scope.local),
        resources=(
            ("parties", "Directory people and organizations", PartyListInput),
            ("affiliations", "Directory affiliations", ListInput),
            ("addresses", "Directory addresses", ListInput),
        ),
    )

    directory = OwnerRoutes(registry, "base", "base/base-directory")
    for resource in ("parties", "affiliations", "addresses"):
        directory.write(
            f"base_{resource}_create",
            "POST",
            f"/{resource}/",
            f"Create a shared Directory record in {resource}.",
            permission="write",
        )
        directory.write(
            f"base_{resource}_update",
            "PUT",
            f"/{resource}/{{uid}}/",
            f"Edit a shared Directory record in {resource} using its version.",
            permission="write",
        )
