"""Explicit registry containing only Projects-owned models."""

from src.erp.projects.metatables import MODELS


def metatable_provider_models():
    return MODELS
