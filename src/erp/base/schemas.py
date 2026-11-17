"""Strict public input contracts. Clients cannot set identity, version or audit metadata."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .identity_contracts import IdentityDetails, RelationshipDetails

Name = Annotated[str, Field(min_length=1, max_length=200)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: Name


class CountryInput(Input):
    code: str = Field(pattern=r"^[A-Z]{2}$")


class SubdivisionInput(Input):
    code: str = Field(pattern=r"^[A-Z]{2}-[A-Z0-9]{1,8}$")
    country_uid: UUID


class LanguageInput(Input):
    code: str = Field(pattern=r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-(?:[A-Z]{2}|[0-9]{3}))?$")


class CurrencyInput(Input):
    code: str = Field(pattern=r"^[A-Z]{3}$")
    symbol: str = Field(min_length=1, max_length=12)
    minor_units: int = Field(ge=0, le=6, strict=True)
    rounding: Literal["half_even", "half_up"] = "half_even"


class PartyInput(Input):
    name: str = Field(min_length=1, max_length=511)
    identity: IdentityDetails = Field(default_factory=IdentityDetails)
    kind: Literal["person", "organization"]
    emails: list[EmailStr] = Field(default_factory=list, max_length=20)
    phones: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=20
    )
    language_uid: UUID | None = None

    @model_validator(mode="after")
    def identity_consistency(self):
        if len({str(value).casefold() for value in self.emails}) != len(self.emails) or len(
            set(self.phones)
        ) != len(self.phones):
            raise ValueError("Contact methods must be unique")
        if self.kind == "person" and (self.identity.first_name or self.identity.last_name):
            self.identity.name_style = "structured"
            self.name = " ".join(
                value for value in (self.identity.first_name, self.identity.last_name) if value
            ).strip()
        return self


class AffiliationInput(Input, RelationshipDetails):
    person_uid: UUID
    organization_uid: UUID
    role: str = Field(min_length=1, max_length=150)
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="before")
    @classmethod
    def unify_dates(cls, values):
        values = dict(values)
        for exact, period in (("starts_on", "started_period"), ("ends_on", "ended_period")):
            day, partial = values.get(exact), values.get(period)
            if day and partial and str(day) != partial:
                raise ValueError("Exact dates and periods must agree")
            if day and not partial:
                values[period] = str(day)
            elif partial:
                values[exact] = partial if len(partial) == 10 else None
        if values.get("ended_period") and "status" not in values:
            values["status"] = "former"
        return values

    @model_validator(mode="after")
    def dates(self):
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("End date must not precede start date")
        if self.person_uid == self.organization_uid:
            raise ValueError("Person and organization must differ")
        return self


class AddressInput(Input):
    party_uid: UUID
    country_uid: UUID
    subdivision_uid: UUID | None = None
    street: str = Field(min_length=1, max_length=500)
    city: str = Field(min_length=1, max_length=150)
    postal_code: str = Field(default="", max_length=30)


class OperatingCompanyInput(Input):
    party_uid: UUID
    currency_uid: UUID
    parent_uid: UUID | None = None


class NumberSequenceInput(Input):
    code: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,59}$")
    operating_company_uid: UUID | None = None
    prefix: str = Field(default="", max_length=30)
    padding: int = Field(default=6, ge=1, le=12, strict=True)


class PreferenceInput(Input):
    name: Name = "Preferences"
    language_uid: UUID | None = None
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use an IANA timezone name") from None
        return value


class SettingsInput(PreferenceInput):
    name: Name = "Shared defaults"
    currency_uid: UUID | None = None
    operating_company_uid: UUID | None = None


class VersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)


class AllocationInput(VersionInput):
    request_uid: UUID


class RoundInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: str = Field(pattern=r"^-?[0-9]{1,24}(?:\.[0-9]{1,12})?$")


INPUTS = {
    "countries": CountryInput,
    "subdivisions": SubdivisionInput,
    "languages": LanguageInput,
    "currencies": CurrencyInput,
    "parties": PartyInput,
    "affiliations": AffiliationInput,
    "addresses": AddressInput,
    "operating-companies": OperatingCompanyInput,
    "number-sequences": NumberSequenceInput,
    "settings": SettingsInput,
    "preferences": PreferenceInput,
}
