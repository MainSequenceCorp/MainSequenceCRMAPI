"""Optional owner access contracts; standalone Collaboration has no business prerequisite."""

from .errors import CollaborationError


class Dependencies:
    def __init__(self, projects_factory=None):
        self.projects_factory = projects_factory

    def projects(self):
        if self.projects_factory is None:
            raise CollaborationError(
                503,
                "projects_unavailable",
                "Project discussions are unavailable; shared discussions remain available",
            )
        return self.projects_factory()

    def project(self, uid, *, write=False):
        return self.projects().record(uid, write=write)
