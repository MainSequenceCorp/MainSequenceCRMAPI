"""Lazy Projects adapter preserves the effective caller's owner permissions."""


def configured_projects(*, local=False):
    from api.erp.projects.identity import actor_and_capabilities
    from src.erp.projects.service import Service
    from src.erp.projects.store import Store

    actor, caps = actor_and_capabilities(local=local)
    return ProjectsPort(Service(Store(local_only=local), actor, caps, None))


class ProjectsPort:
    def __init__(self, service):
        self.service = service

    def record(self, uid, *, write=False):
        from src.erp.projects.errors import ProjectsError

        from .errors import CollaborationError

        try:
            self.service.require("projects.write" if write else "projects.read")
            return self.service.get("projects", uid)
        except ProjectsError as exc:
            if exc.status in {403, 404}:
                raise CollaborationError(
                    404,
                    "unavailable_discussion",
                    "Linked discussion or project is unavailable to this caller",
                ) from exc
            raise CollaborationError(exc.status, exc.code, exc.message) from exc

    def collection(self, **query):
        from src.erp.projects.errors import ProjectsError

        from .errors import CollaborationError

        try:
            return self.service.collection("projects", **query)
        except ProjectsError as exc:
            raise CollaborationError(exc.status, exc.code, exc.message) from exc
