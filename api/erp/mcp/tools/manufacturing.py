"""Bills of materials and atomic production stock workflows."""

from ..owner_routes import OwnerRoutes


def register_tools(registry):
    manufacturing = OwnerRoutes(registry, "manufacturing", "manufacturing/manufacturing-production")
    for resource, label in (("boms", "bills of materials"), ("orders", "production orders")):
        stem = f"manufacturing_{resource}"
        fixed = {"resource": resource}
        manufacturing.read(
            f"{stem}_list", "/{resource}/", f"Find {label}.", fixed=fixed, permission="read"
        )
        manufacturing.read(
            f"{stem}_get",
            "/{resource}/{uid}/",
            f"Read one of the {label} by UID.",
            fixed=fixed,
            permission="read",
        )
    manufacturing.write(
        "manufacturing_boms_create",
        "POST",
        "/boms/",
        "Create a draft bill of materials.",
        permission="configure",
    )
    manufacturing.write(
        "manufacturing_boms_update",
        "PUT",
        "/boms/{uid}/",
        "Edit a draft bill of materials.",
        permission="configure",
    )
    for action in ("activate", "archive"):
        manufacturing.write(
            f"manufacturing_boms_{action}",
            "POST",
            "/boms/{uid}/{action}/",
            f"{action.capitalize()} an eligible bill of materials.",
            fixed={"action": action},
            permission="configure",
        )
    manufacturing.write(
        "manufacturing_orders_create",
        "POST",
        "/orders/",
        "Create a draft production order from an active recipe.",
        permission="write",
    )
    for action in ("reserve", "complete", "cancel"):
        manufacturing.write(
            f"manufacturing_orders_{action}",
            "POST",
            "/orders/{uid}/{action}/",
            f"{action.capitalize()} the order through the existing production and stock transaction.",
            fixed={"action": action},
            permission="manage",
        )
    for action in ("start", "finish"):
        manufacturing.write(
            f"manufacturing_steps_{action}",
            "POST",
            "/orders/{uid}/steps/{step_uid}/" + action + "/",
            f"{action.capitalize()} a specified production step.",
            permission="manage",
        )
    manufacturing.read(
        "manufacturing_orders_valuation",
        "/orders/{uid}/valuation/",
        "Read Finance valuation for the selected production order.",
        permission="read",
        required_modules=("finance",),
    )
