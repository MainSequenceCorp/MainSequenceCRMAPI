"""Explicit application composition; storage is never deleted by disablement."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    key: str
    api_prefix: str
    migration_provider: str
    prerequisites: tuple[str, ...] = ()


MODULES = {"base": Module("base", "/api/base/v1", "src.erp.base.migrations:migration")}


def resolve_modules(enabled):
    selected = set(enabled)
    if selected - MODULES.keys():
        raise ValueError("Unknown ERP module")
    result, visiting = [], set()

    def visit(key):
        if key in visiting:
            raise ValueError("ERP module dependency cycle")
        if MODULES[key] in result:
            return
        visiting.add(key)
        for dependency in MODULES[key].prerequisites:
            if dependency not in selected:
                raise ValueError(f"{key} requires enabled module {dependency}")
            visit(dependency)
        visiting.remove(key)
        result.append(MODULES[key])

    for key in sorted(selected):
        visit(key)
    return tuple(result)
