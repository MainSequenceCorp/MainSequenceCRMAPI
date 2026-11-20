"""Projects, tasks, time and service order handoffs."""

from ..owner_routes import OwnerRoutes


def register_tools(registry):
    projects = OwnerRoutes(registry, "projects", "projects/projects-delivery")
    for resource, label in (("projects", "projects"), ("tasks", "project tasks")):
        stem, path = f"projects_{resource}", f"/{resource}/"
        projects.read(f"{stem}_list", path, f"Find {label}.", permission="read")
        projects.read(
            f"{stem}_get", path + "{uid}/", f"Read one of the {label} by UID.", permission="read"
        )
        projects.write(
            f"{stem}_create", "POST", path, f"Create a record in {label}.", permission="write"
        )
        projects.write(
            f"{stem}_update",
            "PUT",
            path + "{uid}/",
            f"Edit one of the {label} at its expected version.",
            permission="write",
        )
    for action in ("start", "deliver", "close", "reopen", "cancel"):
        projects.write(
            f"projects_projects_{action}",
            "POST",
            "/projects/{uid}/actions/{action}/",
            f"{action.capitalize()} a project at its expected version.",
            fixed={"action": action},
            permission="manage",
        )
    projects.write(
        "projects_projects_create_from_sales",
        "POST",
        "/projects/from-sales/",
        "Create a linked project from a confirmed Sales service order.",
        permission="manage",
        required_modules=("sales",),
    )
    projects.write(
        "projects_projects_bill",
        "POST",
        "/projects/{uid}/bill/",
        "Create a draft invoice for a delivered project through the owner handoff.",
        permission="manage",
        required_modules=("sales", "finance"),
    )
    projects.write(
        "projects_tasks_set_state",
        "POST",
        "/tasks/{uid}/state/",
        "Change a project task state using its expected version.",
        permission="write",
    )
    projects.read(
        "projects_time_entries_list",
        "/tasks/{uid}/time/",
        "List recorded work for a specified project task UID.",
        permission="read",
    )
    projects.read(
        "projects_time_entries_get",
        "/time-entries/{uid}/",
        "Read one recorded time entry.",
        permission="read",
    )
    projects.write(
        "projects_time_entries_create",
        "POST",
        "/tasks/{uid}/time/",
        "Record time against the specified project task UID.",
        permission="write",
    )
    projects.write(
        "projects_time_entries_void",
        "POST",
        "/time-entries/{uid}/void/",
        "Void an eligible time entry with the required reason and version.",
        permission="write",
    )
