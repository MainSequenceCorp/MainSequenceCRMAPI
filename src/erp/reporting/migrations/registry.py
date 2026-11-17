from metatables.migrations import build_metatable_model_registry
from src.erp.reporting.metatables import MODELS


def metatable_provider_models():
    return build_metatable_model_registry(list(MODELS))
