"""Strict Catalog API inputs; decimals travel as strings without float coercion."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DecimalText = Annotated[
    str, Field(pattern=r"^-?(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?$", max_length=32, strict=True)
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._-]{0,63}$")
    description: str = Field(default="", max_length=4000)


class UnitGroupInput(Input):
    pass


class CategoryInput(Input):
    parent_uid: UUID | None = None


class UnitInput(Input):
    group_uid: UUID
    factor: DecimalText = "1"
    is_reference: bool = Field(default=False, strict=True)
    rounding_increment: DecimalText = "0.01"

    @field_validator("factor", "rounding_increment")
    @classmethod
    def positive(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("Factor and rounding increment must be positive")
        return value.rstrip("0").rstrip(".") if "." in value else value

    @model_validator(mode="after")
    def reference_factor(self):
        if self.is_reference and self.factor != "1":
            raise ValueError("A reference unit must have factor 1")
        return self


class ItemInput(Input):
    kind: Literal["product", "service"]
    unit_uid: UUID
    category_uid: UUID
    purchase_unit_uid: UUID | None = None
    sale_description: str = Field(default="", max_length=4000)
    purchase_description: str = Field(default="", max_length=4000)
    saleable: bool = Field(default=True, strict=True)
    purchasable: bool = Field(default=True, strict=True)


class VersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)


class ConvertInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: DecimalText
    from_unit_uid: UUID
    to_unit_uid: UUID
    rounding: Literal["up", "half_up", "half_even"] = "up"


INPUTS = {
    "items": ItemInput,
    "categories": CategoryInput,
    "units": UnitInput,
    "unit-groups": UnitGroupInput,
}
