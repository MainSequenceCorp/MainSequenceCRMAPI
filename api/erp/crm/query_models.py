"""Closed Pydantic schemas for HTTP URL parameters only."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from api.erp.collections import CollectionParameters, CollectionScopeParameters

DiscoveryQuery = CollectionScopeParameters


class CollectionQuery(CollectionParameters):
    # Keep the existing CRM wire limit. New ERP routes use the shared bound.
    page_index: int = Field(default=0, ge=0)


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_index: int = Field(default=0, ge=0)
    page_size: int = Field(default=25, ge=1, le=100)


class BoardQuery(DiscoveryQuery):
    page_size: int = Field(default=25, ge=1, le=100)


class StageCardsQuery(BoardQuery):
    expected_board_version: int = Field(ge=0)
    cursor: int = Field(default=0, ge=0)
