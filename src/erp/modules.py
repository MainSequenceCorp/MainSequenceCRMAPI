"""Explicit application composition; storage is never deleted by disablement."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    key: str
    api_prefix: str
    migration_provider: str
    prerequisites: tuple[str, ...] = ()


MODULES = {
    "manufacturing": Module(
        "manufacturing",
        "/api/manufacturing/v1",
        "src.erp.manufacturing.migrations:migration",
        ("base", "catalog", "inventory"),
    ),
    "purchasing": Module(
        "purchasing",
        "/api/purchasing/v1",
        "src.erp.purchasing.migrations:migration",
        ("base", "catalog"),
    ),
    "inventory": Module(
        "inventory",
        "/api/inventory/v1",
        "src.erp.inventory.migrations:migration",
        ("base", "catalog"),
    ),
    "marketing": Module(
        "marketing", "/api/marketing/v1", "src.erp.marketing.migrations:migration", ("base",)
    ),
    "collaboration": Module(
        "collaboration", "/api/collaboration/v1", "src.erp.collaboration.migrations:migration"
    ),
    "people": Module("people", "/api/people/v1", "src.erp.people.migrations:migration", ("base",)),
    "projects": Module(
        "projects", "/api/projects/v1", "src.erp.projects.migrations:migration", ("base",)
    ),
    "finance": Module(
        "finance", "/api/finance/v1", "src.erp.finance.migrations:migration", ("base",)
    ),
    "sales": Module(
        "sales", "/api/sales/v1", "src.erp.sales.migrations:migration", ("base", "catalog")
    ),
    "base": Module("base", "/api/base/v1", "src.erp.base.migrations:migration"),
    "catalog": Module("catalog", "/api/catalog/v1", "src.erp.catalog.migrations:migration"),
    "crm": Module("crm", "/api/crm/v1", "src.erp.crm.migrations:migration", ("base",)),
}


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
