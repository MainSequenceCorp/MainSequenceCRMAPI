"""Catalog lookups and unit conversion through the Catalog owner."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from api.erp.catalog.main import service_for
from src.erp.catalog.schemas import ConvertInput

from ..contracts import ListInput
from ..owner_routes import OwnerRoutes
from ..registry import register_reads


class ItemListInput(ListInput):
    kind: Literal["product", "service"] | None = None


class UnitListInput(ListInput):
    group_uid: UUID | None = None


class Conversion(BaseModel):
    quantity: str
    rounded: bool
    from_unit_uid: UUID
    to_unit_uid: UUID
    from_unit_version: int
    to_unit_version: int
    rounding: Literal["up", "half_up", "half_even"]
    rounding_increment: str


def _service(scope):
    return service_for(scope.apps["catalog"], local=scope.local)


def register_tools(registry):
    skill = "catalog/catalog-items"
    register_reads(
        registry,
        owner="catalog",
        skill=skill,
        service=_service,
        resources=(
            ("items", "Catalog items", ItemListInput),
            ("categories", "Catalog categories", ListInput),
            ("units", "Catalog units", UnitListInput),
            ("unit-groups", "Catalog unit groups", ListInput),
        ),
    )
    registry.read(
        "catalog_units_convert",
        description="Convert a decimal quantity between active units.",
        owner="catalog",
        capabilities=("catalog.read",),
        skill=skill,
        inputs=ConvertInput,
        output=Conversion,
        handler=lambda scope, args: _service(scope).convert(args.model_dump()),
    )

    catalog = OwnerRoutes(registry, "catalog", skill)
    for resource in ("items", "categories", "units", "unit-groups"):
        stem = "catalog_" + resource.replace("-", "_")
        permission = "write" if resource == "items" else "configure"
        catalog.write(
            f"{stem}_create",
            "POST",
            f"/{resource}/",
            f"Create a Catalog record in {resource}.",
            permission=permission,
        )
        catalog.write(
            f"{stem}_update",
            "PUT",
            f"/{resource}/{{uid}}/",
            f"Edit a Catalog record in {resource} using its expected version.",
            permission=permission,
        )
