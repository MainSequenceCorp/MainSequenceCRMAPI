"""Optional Projects owner service; importing People core does not import Projects."""


def configured_projects(*, local=False):
    from api.erp.base.identity import actor_and_capabilities as base_identity
    from api.erp.projects.identity import actor_and_capabilities
    from src.erp.base.service import Service as BaseService
    from src.erp.base.store import Store as BaseStore
    from src.erp.projects.dependencies import Dependencies
    from src.erp.projects.service import Service
    from src.erp.projects.store import Store

    actor, caps = actor_and_capabilities(local=local)
    ba, bc = base_identity(local=local)
    return ProjectsPort(
        Service(
            Store(local_only=local),
            actor,
            caps,
            Dependencies(BaseService(BaseStore(local_only=local), ba, bc)),
        )
    )


class ProjectsPort:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def call(self, method, *args, **kwargs):
        from src.erp.people.errors import PeopleError
        from src.erp.projects.errors import ProjectsError

        try:
            return getattr(self.service, method)(*args, **kwargs)
        except ProjectsError as exc:
            raise PeopleError(exc.status, exc.code, exc.message) from exc

    def get(self, *args, **kwargs):
        return self.call("get", *args, **kwargs)

    def collection(self, *args, **kwargs):
        return self.call("collection", *args, **kwargs)

    def plan_assignment(self, *args, **kwargs):
        return self.call("plan_assignment", *args, **kwargs)
