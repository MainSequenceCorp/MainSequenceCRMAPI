"""Explicit application composition; storage is never deleted by disablement."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Module:
    key: str
    title: str
    api_prefix: str
    migration_provider: str
    prerequisites: tuple[str, ...] = ()


MODULES = {
    "reporting": Module(
        "reporting",
        "Reporting and automation",
        "/api/reporting/v1",
        "src.erp.reporting.migrations:migration",
    ),
    "commerce": Module(
        "commerce",
        "Website and commerce",
        "/api/commerce/v1",
        "src.erp.commerce.migrations:migration",
        ("base", "catalog"),
    ),
    "manufacturing": Module(
        "manufacturing",
        "Manufacturing",
        "/api/manufacturing/v1",
        "src.erp.manufacturing.migrations:migration",
        ("base", "catalog", "inventory"),
    ),
    "purchasing": Module(
        "purchasing",
        "Purchasing",
        "/api/purchasing/v1",
        "src.erp.purchasing.migrations:migration",
        ("base", "catalog"),
    ),
    "inventory": Module(
        "inventory",
        "Inventory",
        "/api/inventory/v1",
        "src.erp.inventory.migrations:migration",
        ("base", "catalog"),
    ),
    "marketing": Module(
        "marketing",
        "Marketing",
        "/api/marketing/v1",
        "src.erp.marketing.migrations:migration",
        ("base",),
    ),
    "collaboration": Module(
        "collaboration",
        "Collaboration",
        "/api/collaboration/v1",
        "src.erp.collaboration.migrations:migration",
    ),
    "people": Module(
        "people", "People", "/api/people/v1", "src.erp.people.migrations:migration", ("base",)
    ),
    "projects": Module(
        "projects",
        "Projects and services",
        "/api/projects/v1",
        "src.erp.projects.migrations:migration",
        ("base",),
    ),
    "finance": Module(
        "finance", "Finance", "/api/finance/v1", "src.erp.finance.migrations:migration", ("base",)
    ),
    "sales": Module(
        "sales", "Sales", "/api/sales/v1", "src.erp.sales.migrations:migration", ("base", "catalog")
    ),
    "base": Module(
        "base", "Business Directory", "/api/base/v1", "src.erp.base.migrations:migration"
    ),
    "catalog": Module(
        "catalog", "Catalog", "/api/catalog/v1", "src.erp.catalog.migrations:migration"
    ),
    "crm": Module("crm", "CRM", "/api/crm/v1", "src.erp.crm.migrations:migration", ("base",)),
}

REQUIRED_MODULES = frozenset({"base"})
OPTIONAL_MODULES = frozenset(MODULES) - REQUIRED_MODULES


@dataclass(frozen=True)
class WorkflowDependency:
    key: str
    owner: str
    title: str
    required_modules: tuple[str, ...]
    data_source_rule: Literal["owner_contract", "same_source_read", "same_source_transaction"]
    condition: str | None = None


OWNER = "owner_contract"
READ = "same_source_read"
ATOMIC = "same_source_transaction"
WORKFLOWS = (
    WorkflowDependency("opportunity_link", "sales", "CRM opportunity linking", ("crm",), OWNER),
    WorkflowDependency("order_to_invoice", "finance", "Sales order to invoice", ("sales",), ATOMIC),
    WorkflowDependency(
        "service_order", "projects", "Create a project from an order", ("sales",), ATOMIC
    ),
    WorkflowDependency(
        "project_invoice", "projects", "Bill a delivered project", ("sales", "finance"), ATOMIC
    ),
    WorkflowDependency("staff_task", "people", "Staff a project task", ("projects",), ATOMIC),
    WorkflowDependency(
        "project_discussions", "collaboration", "Project discussions", ("projects",), OWNER
    ),
    WorkflowDependency("follow_up", "marketing", "CRM follow-up links", ("crm",), OWNER),
    WorkflowDependency("order_delivery", "inventory", "Sales order delivery", ("sales",), ATOMIC),
    WorkflowDependency("stock_valuation", "inventory", "Stock valuation", ("finance",), ATOMIC),
    WorkflowDependency(
        "valued_return",
        "inventory",
        "Returns of valued stock",
        ("finance",),
        ATOMIC,
        "finance_posted",
    ),
    WorkflowDependency("valuation_detail", "inventory", "Valuation details", ("finance",), READ),
    WorkflowDependency(
        "physical_receipt", "purchasing", "Physical receipts", ("inventory",), ATOMIC
    ),
    WorkflowDependency("vendor_bill", "purchasing", "Draft vendor bills", ("finance",), ATOMIC),
    WorkflowDependency(
        "physical_vendor_bill",
        "purchasing",
        "Bills for physical receipts",
        ("finance", "inventory"),
        ATOMIC,
        "physical_receipts",
    ),
    WorkflowDependency(
        "production_stock", "manufacturing", "Production stock movements", ("inventory",), ATOMIC
    ),
    WorkflowDependency(
        "production_valuation",
        "manufacturing",
        "Production valuation",
        ("inventory", "finance"),
        ATOMIC,
    ),
    WorkflowDependency("checkout", "commerce", "Checkout", ("sales",), ATOMIC),
    WorkflowDependency(
        "checkout_invoice", "commerce", "Checkout invoicing", ("sales", "finance"), ATOMIC
    ),
    WorkflowDependency(
        "recorded_payment", "commerce", "Recorded payment status", ("finance",), READ, "invoiced"
    ),
    WorkflowDependency(
        "commercial_report", "reporting", "Commercial reports", ("sales", "finance"), READ
    ),
    WorkflowDependency(
        "operations_report",
        "reporting",
        "Operations reports",
        ("projects", "inventory", "purchasing", "manufacturing"),
        READ,
    ),
)


def module_closure(keys):
    """Return a request's modules and all registered prerequisites."""
    selected = set(keys)
    pending = list(selected)
    while pending:
        key = pending.pop()
        if key not in MODULES:
            raise ValueError(f"Unknown ERP module: {key}")
        missing = set(MODULES[key].prerequisites) - selected
        selected.update(missing)
        pending.extend(missing)
    return frozenset(selected)


def active_modules(optional_keys):
    optional = set(optional_keys)
    if optional - OPTIONAL_MODULES:
        raise ValueError("Only optional ERP modules can be selected")
    return resolve_modules(optional | REQUIRED_MODULES)


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
