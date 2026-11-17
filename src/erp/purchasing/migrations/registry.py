from __future__ import annotations

from typing import Any

from metatables.migrations import build_metatable_model_registry
from src.erp.purchasing.metatables import MODELS, Base


def _metatable_model_sources() -> list[type[Any]]:
    return list(MODELS)


def metatable_provider_models() -> list[type[Any]]:
    return build_metatable_model_registry(_metatable_model_sources(), base=Base)


__all__ = ["metatable_provider_models"]
