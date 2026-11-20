"""Merchant-owned draft sites and offers, checkout, and grant status."""

from ..owner_routes import OwnerRoutes


def register_tools(registry):
    commerce = OwnerRoutes(registry, "commerce", "commerce/commerce-merchants")
    for resource, label in (
        ("sites", "merchant sites"),
        ("offers", "service offers"),
        ("checkouts", "customer checkout records"),
        ("grants", "portal access grant status"),
    ):
        stem = f"commerce_{resource}"
        fixed = {"resource": resource}
        commerce.read(
            f"{stem}_list", "/{resource}/", f"Find {label}.", fixed=fixed, permission="read"
        )
        commerce.read(
            f"{stem}_get",
            "/{resource}/{uid}/",
            f"Read {label} for one UID.",
            fixed=fixed,
            permission="read",
        )
    for resource in ("sites", "offers"):
        stem, path = f"commerce_{resource}", f"/{resource}/"
        commerce.write(
            f"{stem}_create",
            "POST",
            path,
            f"Create a merchant draft in {resource}.",
            permission="configure",
        )
        commerce.write(
            f"{stem}_update",
            "PUT",
            path + "{uid}/",
            f"Edit the selected draft in {resource}.",
            permission="configure",
        )
    commerce.read(
        "commerce_checkouts_payment_status",
        "/checkouts/{uid}/payment/",
        "Read the recorded payment state for a checkout.",
        permission="read",
    )
    commerce.write(
        "commerce_checkouts_create_invoice",
        "POST",
        "/checkouts/{uid}/invoice/",
        "Create one draft Finance invoice linked to the checkout and confirmed Sales order.",
        permission="manage",
        required_modules=("sales", "finance"),
    )
