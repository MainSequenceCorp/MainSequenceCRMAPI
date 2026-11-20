"""Purchasing orders and guarded receipt and invoice handoffs."""

from ..owner_routes import OwnerRoutes


def register_tools(registry):
    purchasing = OwnerRoutes(registry, "purchasing", "purchasing/purchasing-orders")
    purchasing.read(
        "purchasing_orders_list", "/orders/", "Find purchase orders.", permission="read"
    )
    purchasing.read(
        "purchasing_orders_get",
        "/orders/{uid}/",
        "Read a purchase order, lines and handoff references.",
        permission="read",
    )
    purchasing.read(
        "purchasing_orders_fulfillment",
        "/orders/{uid}/fulfillment/",
        "Read receipt, service acceptance and billing progress.",
        permission="read",
    )
    purchasing.write(
        "purchasing_orders_create",
        "POST",
        "/orders/",
        "Create a draft supplier order.",
        permission="write",
    )
    purchasing.write(
        "purchasing_orders_update",
        "PUT",
        "/orders/{uid}/",
        "Edit a draft supplier order.",
        permission="write",
    )
    for action, command in (
        ("request_quote", "rfq"),
        ("confirm", "confirm"),
        ("cancel", "cancel"),
        ("reopen", "reopen"),
        ("close", "close"),
    ):
        purchasing.write(
            f"purchasing_orders_{action}",
            "POST",
            "/orders/{uid}/{action}/",
            f"Apply the {command} transition to the selected purchase order.",
            fixed={"action": command},
            permission="manage" if command == "close" else "write",
        )
    purchasing.write(
        "purchasing_order_lines_accept_service",
        "POST",
        "/orders/{uid}/lines/{line_uid}/accept/",
        "Record accepted service against a specific purchase order line.",
        permission="manage",
    )
    purchasing.write(
        "purchasing_order_lines_revoke_acceptance",
        "POST",
        "/orders/{uid}/lines/{line_uid}/revoke/",
        "Revoke an eligible unbilled service acceptance.",
        permission="manage",
    )
    purchasing.write(
        "purchasing_order_lines_receive_stock",
        "POST",
        "/orders/{uid}/lines/{line_uid}/receipt/",
        "Receive a physical delivery and link it to the purchase line in one transaction.",
        permission="manage",
        required_modules=("inventory",),
    )
    purchasing.write(
        "purchasing_orders_create_vendor_bill",
        "POST",
        "/orders/{uid}/bill/",
        "Create a draft vendor bill from the purchase order and its eligible receipts or acceptances.",
        permission="manage",
        required_modules=("finance",),
    )
