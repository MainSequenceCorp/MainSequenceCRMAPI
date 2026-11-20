"""Bounded request and response contracts for the ERP MCP pilot."""

from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListInput(EmptyInput):
    page_index: int = Field(0, ge=0, le=100_000, strict=True)
    page_size: int = Field(25, ge=1, le=100, strict=True)
    search: str = Field("", max_length=200)
    archived: Annotated[bool, Field(strict=True)] = False


class GetInput(EmptyInput):
    uid: UUID


class Record(BaseModel):
    model_config = ConfigDict(extra="allow")

    uid: UUID
    version: int


class PageInfo(BaseModel):
    pageIndex: int
    pageSize: int
    totalItems: int
    hasNextPage: bool
    hasPreviousPage: bool


class Collection(BaseModel):
    items: list[Record]
    pageInfo: PageInfo


Result = TypeVar("Result")


class Success(BaseModel, Generic[Result]):
    code: Literal["ok"] = "ok"
    data: Result


class Failure(BaseModel):
    code: Literal[
        "invalid_arguments",
        "validation_error",
        "not_found",
        "forbidden",
        "module_disabled",
        "unavailable",
        "conflict",
        "result_too_large",
        "internal_error",
    ]
    message: str
    data: dict[str, Any] | None = None
