"""Subscriber state, draft mailings, and verified local simulation."""

from ..owner_routes import OwnerRoutes


def register_tools(registry):
    marketing = OwnerRoutes(registry, "marketing", "marketing/marketing-mailings")
    for resource in ("subscribers", "mailings"):
        stem, path = f"marketing_{resource}", f"/{resource}/"
        marketing.read(
            f"{stem}_list",
            "/{resource}/",
            f"Find {resource}.",
            fixed={"resource": resource},
            permission="read",
        )
        marketing.read(
            f"{stem}_get",
            "/{resource}/{uid}/",
            f"Read one of the {resource} by UID.",
            fixed={"resource": resource},
            permission="read",
        )
        marketing.write(
            f"{stem}_create", "POST", path, f"Create a record in {resource}.", permission="write"
        )
    marketing.write(
        "marketing_subscribers_set_subscription",
        "POST",
        "/subscribers/{uid}/subscription/",
        "Record the subscriber's authorized subscription change.",
        permission="write",
    )
    marketing.write(
        "marketing_mailings_update",
        "PUT",
        "/mailings/{uid}/",
        "Edit a draft mailing.",
        permission="write",
    )
    marketing.write(
        "marketing_mailings_queue",
        "POST",
        "/mailings/{uid}/queue/",
        "Queue the selected mailing for the local capture workflow.",
        permission="manage",
        local_only=True,
    )
    marketing.write(
        "marketing_mailings_cancel",
        "POST",
        "/mailings/{uid}/cancel/",
        "Cancel an eligible mailing at its expected version.",
        permission="manage",
    )
    marketing.write(
        "marketing_mailings_capture",
        "POST",
        "/mailings/{uid}/capture/",
        "Capture a queued mailing in local simulation without delivering mail.",
        permission="manage",
        local_only=True,
    )
    marketing.read(
        "marketing_recipients_list",
        "/mailings/{uid}/recipients/",
        "List recipients of the specified mailing.",
        permission="read",
    )
    marketing.read(
        "marketing_recipients_get",
        "/recipients/{uid}/",
        "Read one mailing recipient.",
        permission="read",
    )
    marketing.read(
        "marketing_recipients_events",
        "/recipients/{uid}/events/",
        "Read the recipient's recorded mailing events.",
        permission="read",
    )
    marketing.write(
        "marketing_recipients_add",
        "POST",
        "/mailings/{uid}/recipients/",
        "Add an eligible recipient to the specified draft mailing.",
        permission="write",
    )
    marketing.write(
        "marketing_recipients_remove",
        "POST",
        "/recipients/{uid}/remove/",
        "Remove an eligible recipient using the required versions.",
        permission="write",
    )
    marketing.write(
        "marketing_recipients_simulate",
        "POST",
        "/recipients/{uid}/simulate/",
        "Record a local simulated recipient event without contacting the recipient.",
        permission="manage",
        local_only=True,
    )
    marketing.write(
        "marketing_recipients_link_followup",
        "POST",
        "/recipients/{uid}/followup/",
        "Link an existing eligible CRM follow-up task to the recipient.",
        permission="manage",
        required_modules=("crm",),
    )
