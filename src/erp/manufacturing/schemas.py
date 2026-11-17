"""Strict exact quantities and explicit optimistic versions for Manufacturing."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Version = Annotated[int, Field(ge=1, strict=True)]
DecimalText = Annotated[
    str, Field(pattern=r"^(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?$", max_length=32, strict=True)
]
Reference = Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9._/-]{0,63}$")]
Operation = Annotated[str, Field(min_length=1, max_length=200)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Quantity(Input):
    quantity: DecimalText

    @field_validator("quantity")
    @classmethod
    def positive(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("Quantity must be positive")
        return value


class Component(Quantity):
    item_uid: UUID


class BomInput(Component):
    name: Reference
    components: list[Component] = Field(min_length=1, max_length=8)
    operations: list[Operation] = Field(min_length=1, max_length=20)


class BomCreate(BomInput):
    request_uid: UUID


class BomUpdate(BomInput):
    expected_version: Version


class ProductionCreate(Quantity):
    request_uid: UUID
    name: Reference
    bom_uid: UUID
    expected_bom_version: Version
    operating_company_uid: UUID
    source_uid: UUID
    destination_uid: UUID
    production_location_uid: UUID


class VersionInput(Input):
    expected_version: Version


class StepStart(VersionInput):
    expected_step_version: Version


class StepFinish(StepStart):
    minutes: int = Field(ge=0, le=600000, strict=True)
    evidence: str = Field(min_length=1, max_length=2000)
