"""Base reads and an optional public Projects adapter; no foreign models."""

from .errors import PeopleError


class Dependencies:
    def __init__(self, base, projects_factory=None):
        self.base, self.projects_factory = base, projects_factory

    def ready(self):
        self.base.require("base.read")
        return {"base": self.base.store.data_source_uid}

    def base_record(self, resource, uid):
        row = self.base.get(resource, uid)
        if row.get("archived_at"):
            raise PeopleError(422, "inactive_reference", "Choose active shared records")
        return row

    def projects(self):
        if self.projects_factory is None:
            raise PeopleError(
                503,
                "projects_unavailable",
                "Projects staffing is unavailable; People records remain available",
            )
        return self.projects_factory()

    def collection(self, resource, **query):
        if resource == "tasks":
            return self.projects().collection("tasks", **query)
        if resource not in {"people", "companies"}:
            raise PeopleError(404, "not_found", "Unknown reference")
        return self.base.collection(
            "operating-companies" if resource == "companies" else "parties",
            **query,
            **({"kind": "person"} if resource == "people" else {}),
        )
