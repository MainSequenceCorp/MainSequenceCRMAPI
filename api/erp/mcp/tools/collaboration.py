"""Internal discussion threads and message revisions."""

from ..owner_routes import OwnerRoutes


def register_tools(registry):
    chat = OwnerRoutes(registry, "collaboration", "collaboration/collaboration-discussions")
    chat.read(
        "collaboration_discussions_list",
        "/discussions/",
        "Find discussions visible to the requester.",
        permission="read",
    )
    chat.read(
        "collaboration_discussions_get",
        "/discussions/{uid}/",
        "Read an authorized discussion.",
        permission="read",
    )
    chat.write(
        "collaboration_discussions_create",
        "POST",
        "/discussions/",
        "Open an internal discussion.",
        permission="write",
    )
    chat.write(
        "collaboration_discussions_update",
        "PUT",
        "/discussions/{uid}/",
        "Edit a discussion's title and description at its current version.",
        permission="write",
    )
    for action in ("close", "reopen", "archive", "restore"):
        chat.write(
            f"collaboration_discussions_{action}",
            "POST",
            "/discussions/{uid}/actions/{action}/",
            f"{action.capitalize()} a discussion at its expected version.",
            fixed={"action": action},
            permission="manage",
        )
    chat.read(
        "collaboration_messages_list",
        "/discussions/{uid}/messages/",
        "Read a bounded page of messages in the specified discussion.",
        permission="read",
    )
    chat.read(
        "collaboration_messages_get",
        "/messages/{uid}/",
        "Read an authorized message.",
        permission="read",
    )
    chat.read(
        "collaboration_messages_revisions",
        "/messages/{uid}/revisions/",
        "Read permitted revisions of one message.",
        permission="read",
    )
    chat.write(
        "collaboration_messages_post",
        "POST",
        "/discussions/{uid}/messages/",
        "Post a message in the specified internal discussion.",
        permission="write",
    )
    chat.write(
        "collaboration_messages_edit",
        "PUT",
        "/messages/{uid}/",
        "Edit an eligible discussion message at its expected version.",
        permission="write",
    )
    chat.write(
        "collaboration_messages_retract",
        "POST",
        "/messages/{uid}/retract/",
        "Retract an eligible discussion message with the required reason.",
        permission="write",
    )
