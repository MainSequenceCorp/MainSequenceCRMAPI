"""Sales quotation and order operations."""

from ..owner_routes import OwnerRoutes


def register_tools(registry):
    sales = OwnerRoutes(registry, "sales", "sales/sales-orders")
    sales.read(
        "sales_orders_list", "/orders/", "Find Sales quotations and orders.", permission="read"
    )
    sales.read(
        "sales_orders_get",
        "/orders/{uid}/",
        "Read an order, lines and downstream references.",
        permission="read",
    )
    sales.write(
        "sales_orders_create",
        "POST",
        "/orders/",
        "Create a draft Sales quotation.",
        permission="write",
    )
    sales.write(
        "sales_orders_update",
        "PUT",
        "/orders/{uid}/",
        "Edit a draft quotation at its expected version.",
        permission="write",
    )
    for action, command in (
        ("quote", "quoted"),
        ("confirm", "confirm"),
        ("cancel", "cancel"),
        ("reopen", "reopen"),
    ):
        sales.write(
            f"sales_orders_{action}",
            "POST",
            "/orders/{uid}/{action}/",
            f"{action.capitalize()} the selected Sales order at its expected version.",
            permission="write",
            fixed={"action": command},
        )
