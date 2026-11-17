from metatables.migrations import build_metatable_model_registry
from src.erp.commerce.metatables import MODELS


def metatable_provider_models():
    return build_metatable_model_registry(list(MODELS))
