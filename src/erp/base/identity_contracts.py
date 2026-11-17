"""Base-owned, lossless shared identity contracts. No domain imports."""

import calendar
from datetime import date
from typing import Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, HttpUrl, model_validator


class AssetReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["external_link"]
    url: AnyUrl
    title: str = Field(max_length=255)
    mime_type: str | None = Field(None, max_length=255)
    source_verified: Literal[False]


class SocialProfiles(BaseModel):
    model_config = ConfigDict(extra="forbid")
    linkedin: HttpUrl | None = None
    x: HttpUrl | None = None
    facebook: HttpUrl | None = None
    instagram: HttpUrl | None = None
    threads: HttpUrl | None = None
    bluesky: HttpUrl | None = None
    mastodon: HttpUrl | None = None
    tiktok: HttpUrl | None = None
    youtube: HttpUrl | None = None
    snapchat: HttpUrl | None = None
    pinterest: HttpUrl | None = None
    reddit: HttpUrl | None = None
    github: HttpUrl | None = None
    gitlab: HttpUrl | None = None
    telegram: HttpUrl | None = None
    discord: HttpUrl | None = None
    whatsapp: HttpUrl | None = None
    wechat: HttpUrl | None = None
    line: HttpUrl | None = None


class IdentityDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name_style: Literal["structured", "unstructured"] = "unstructured"
    first_name: str | None = Field(None, max_length=255)
    last_name: str | None = Field(None, max_length=255)
    gender: str | None = Field(None, max_length=100)
    avatar_ref: AssetReference | None = None
    socials: SocialProfiles = Field(default_factory=SocialProfiles)
    email_labels: dict[str, Literal["work", "home", "other"]] = Field(default_factory=dict)
    phone_labels: dict[str, Literal["work", "home", "other"]] = Field(default_factory=dict)
    website: str | None = None
    linkedin_url: str | None = None
    normalized_domain: str | None = Field(None, max_length=255)
    phone_number: str | None = Field(None, max_length=100)
    address: str | None = None
    zipcode: str | None = Field(None, max_length=40)
    city: str | None = Field(None, max_length=255)
    state_abbr: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=255)
    tax_identifier: str | None = Field(None, max_length=255)
    logo_ref: AssetReference | None = None


def period_bounds(value):
    parts = value.split("-")
    if (
        len(parts) not in (1, 2, 3)
        or len(parts[0]) != 4
        or any(len(part) != 2 for part in parts[1:])
        or not all(part.isascii() and part.isdigit() for part in parts)
    ):
        raise ValueError("Use YYYY, YYYY-MM or YYYY-MM-DD")
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 else None
    if len(parts) == 3:
        exact = date(year, month, int(parts[2]))
        return exact, exact
    if month:
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    return date(year, 1, 1), date(year, 12, 31)


class RelationshipDetails(BaseModel):
    status: Literal["current", "former", "unknown"] = "unknown"
    started_period: str | None = Field(None, max_length=10)
    ended_period: str | None = Field(None, max_length=10)
    job_title: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def valid_periods(self):
        start = period_bounds(self.started_period) if self.started_period else None
        end = period_bounds(self.ended_period) if self.ended_period else None
        if end and self.status != "former":
            raise ValueError("An ended relationship must have former status")
        if start and end and start[0] > end[1]:
            raise ValueError("End period precedes start period")
        return self
