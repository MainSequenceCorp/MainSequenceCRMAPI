"""HTTP inputs for ERP collections using the shared query conventions."""

import json
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.erp.module_access.http import collection_route

PageIndex = Annotated[int, Query(ge=0, le=100000)]
PageSize = Annotated[int, Query(ge=1, le=100)]
SearchText = Annotated[str, Query(max_length=200)]


def collection_get(router, path, **options):
    """Register a GET that authorizes within the shared collection statement."""
    register = router.get(path, **options)

    def decorate(endpoint):
        return register(collection_route(endpoint))

    return decorate


class CollectionScopeParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search: str | None = None
    filters: str = "{}"

    @field_validator("search")
    @classmethod
    def normalize_search(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) > 200:
            raise ValueError("Search exceeds 200 characters")
        return value or None


class CollectionParameters(CollectionScopeParameters):
    ordering: str | None = None
    page_index: int = Field(default=0, ge=0, le=100000)
    page_size: int = Field(default=25, ge=1, le=100)


def decode_filter_object(value: str):
    def unique_keys(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Filters must use unique keys")
            result[key] = item
        return result

    try:
        filters = json.loads(value, object_pairs_hook=unique_keys)
    except json.JSONDecodeError:
        raise ValueError("Filters must be a JSON object") from None
    if not isinstance(filters, dict):
        raise ValueError("Filters must be a JSON object")
    return filters
