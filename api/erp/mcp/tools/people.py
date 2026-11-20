"""Personnel records, staffing, and controlled absence decisions."""

from ..owner_routes import OwnerRoutes


def register_tools(registry):
    people = OwnerRoutes(registry, "people", "people/people-workforce")
    for resource in ("departments", "employees", "absences"):
        stem, path = f"people_{resource}", f"/{resource}/"
        fixed = {"resource": resource}
        people.read(
            f"{stem}_list",
            "/{resource}/",
            f"Find permitted {resource}.",
            fixed=fixed,
            permission="read",
        )
        people.read(
            f"{stem}_get",
            "/{resource}/{uid}/",
            f"Read one of the permitted {resource}.",
            fixed=fixed,
            permission="read",
        )
        people.write(
            f"{stem}_create", "POST", path, f"Create a record in {resource}.", permission="write"
        )
        people.write(
            f"{stem}_update",
            "PUT",
            path + "{uid}/",
            f"Edit a record in {resource} using its version.",
            permission="write",
        )
    for resource in ("employees", "departments"):
        for action in ("archive", "restore"):
            people.write(
                f"people_{resource}_{action}",
                "POST",
                "/{resource}/{uid}/actions/{action}/",
                f"{action.capitalize()} the selected record in {resource}.",
                fixed={"resource": resource, "action": action},
                permission="manage",
            )
    for action in ("submit", "approve", "reject", "cancel"):
        people.write(
            f"people_absences_{action}",
            "POST",
            "/absences/{uid}/actions/{action}/",
            f"{action.capitalize()} a versioned absence request under the owner's approval rules.",
            fixed={"action": action},
            permission="manage" if action in {"approve", "reject"} else "write",
        )
    people.write(
        "people_employees_staff_task",
        "POST",
        "/employees/{uid}/staff/",
        "Assign the employee to a project task through the guarded staffing workflow.",
        permission="manage",
        required_modules=("projects",),
    )
