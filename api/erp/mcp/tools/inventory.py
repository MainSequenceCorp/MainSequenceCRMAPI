"""Locations, stock policy, and owned stock movement commands."""

from ..owner_routes import OwnerRoutes


def register_tools(registry):
    inventory = OwnerRoutes(registry, "inventory", "inventory/inventory-stock")
    for resource in ("locations", "stock-items", "balances", "movements"):
        stem = "inventory_" + resource.replace("-", "_")
        fixed = {"resource": resource}
        inventory.read(
            f"{stem}_list",
            "/{resource}/",
            f"Find stock {resource}.",
            fixed=fixed,
            permission="read",
        )
        inventory.read(
            f"{stem}_get",
            "/{resource}/{uid}/",
            f"Read a record in {resource} by UID.",
            fixed=fixed,
            permission="read",
        )
    inventory.write(
        "inventory_locations_create",
        "POST",
        "/locations/",
        "Create a stock location.",
        permission="configure",
    )
    inventory.write(
        "inventory_locations_update",
        "PUT",
        "/locations/{uid}/",
        "Edit a location at its expected version.",
        permission="configure",
    )
    inventory.write(
        "inventory_stock_items_create",
        "POST",
        "/stock-items/",
        "Create a stock item policy for a Catalog product.",
        permission="configure",
    )
    for resource in ("locations", "stock-items"):
        for action in ("archive", "restore"):
            inventory.write(
                f"inventory_{resource.replace('-', '_')}_{action}",
                "POST",
                "/{resource}/{uid}/" + action + "/",
                f"{action.capitalize()} an eligible {resource} record at its expected version.",
                fixed={"resource": resource},
                permission="configure",
            )
    inventory.write(
        "inventory_movements_create",
        "POST",
        "/movements/",
        "Create a draft owned stock movement.",
        permission="write",
    )
    inventory.write(
        "inventory_movements_create_from_sales",
        "POST",
        "/from-sales/",
        "Create a draft delivery linked to a confirmed Sales order.",
        permission="manage",
        required_modules=("sales",),
    )
    for action in ("prepare", "complete", "cancel"):
        inventory.write(
            f"inventory_movements_{action}",
            "POST",
            "/movements/{uid}/{action}/",
            f"{action.capitalize()} an eligible stock movement at its expected version.",
            fixed={"action": action},
            permission="manage",
        )
