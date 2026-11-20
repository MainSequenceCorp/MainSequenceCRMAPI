"""Governed report runs, bounded exports, and local schedule controls."""

from src.erp.reporting.service import now

from ..owner_routes import OwnerRoutes


def _worker_available(scope):
    last_tick = scope.apps["reporting"].state.worker_ticks.get(str(scope.settings.actor))
    return scope.local and last_tick is not None and (now() - last_tick).total_seconds() < 30


def register_tools(registry):
    reporting = OwnerRoutes(registry, "reporting", "reporting/reporting-runs")
    for resource, label in (("definitions", "report definitions"), ("runs", "saved report runs")):
        stem = f"reporting_{resource}"
        fixed = {"resource": resource}
        reporting.read(
            f"{stem}_list", "/{resource}/", f"Find {label}.", fixed=fixed, permission="read"
        )
        reporting.read(
            f"{stem}_get",
            "/{resource}/{uid}/",
            f"Read one of the {label} by UID.",
            fixed=fixed,
            permission="read",
        )
    reporting.write(
        "reporting_definitions_create",
        "POST",
        "/definitions/",
        "Create a governed report definition.",
        permission="write",
    )
    reporting.write(
        "reporting_definitions_update",
        "PUT",
        "/definitions/{uid}/",
        "Edit a report definition at its version.",
        permission="write",
    )
    for action in ("archive", "restore"):
        reporting.write(
            f"reporting_definitions_{action}",
            "POST",
            "/definitions/{uid}/{action}/",
            f"{action.capitalize()} an eligible saved report definition.",
            fixed={"action": action},
            permission="write",
        )
    reporting.write(
        "reporting_runs_start",
        "POST",
        "/runs/",
        "Queue one run of a selected report definition.",
        permission="run",
    )
    reporting.write(
        "reporting_runs_advance",
        "POST",
        "/runs/{uid}/advance/",
        "Execute one eligible report run through the owner.",
        permission="run",
    )
    for action in ("retry", "recover", "cancel"):
        reporting.write(
            f"reporting_runs_{action}",
            "POST",
            "/runs/{uid}/{action}/",
            f"{action.capitalize()} an eligible report run.",
            fixed={"action": action},
            permission="run",
        )
    for resource in ("result", "rows", "export"):
        reporting.read(
            f"reporting_runs_{resource}",
            f"/runs/{{uid}}/{resource}/",
            f"Read the authorized report run {resource}.",
            permission="read",
        )
    reporting.bind(
        "reporting_runs_verify",
        "POST",
        "/runs/{uid}/verify/",
        "Compare captured results with the current authorized source records.",
        permission="read",
        kind="read",
    )

    schedules = OwnerRoutes(registry, "reporting", "reporting/reporting-schedules")
    schedules.read(
        "reporting_schedules_list",
        "/{resource}/",
        "Find saved report schedules.",
        fixed={"resource": "schedules"},
        permission="read",
    )
    schedules.read(
        "reporting_schedules_get",
        "/{resource}/{uid}/",
        "Read a saved report schedule.",
        fixed={"resource": "schedules"},
        permission="read",
    )
    schedules.write(
        "reporting_schedules_create",
        "POST",
        "/schedules/",
        "Create a paused report schedule when its local worker is available.",
        permission="manage",
        local_only=True,
        available=_worker_available,
    )
    schedules.write(
        "reporting_schedules_update",
        "PUT",
        "/schedules/{uid}/",
        "Edit a schedule at its expected version when its local worker is available.",
        permission="manage",
        local_only=True,
        available=_worker_available,
    )
    schedules.write(
        "reporting_schedules_activate",
        "POST",
        "/schedules/{uid}/{action}/",
        "Activate a reviewed schedule against a ready local worker.",
        fixed={"action": "activate"},
        permission="manage",
        local_only=True,
        available=_worker_available,
    )
    schedules.write(
        "reporting_schedules_pause",
        "POST",
        "/schedules/{uid}/{action}/",
        "Pause a local report schedule at its expected version.",
        fixed={"action": "pause"},
        permission="manage",
        local_only=True,
    )
