import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select

from mainsequence.client import User
from metatables import configure_local_client, upgrade_application
from src.erp.base.metatables import RESOURCES as BASE
from src.erp.base.metatables import AuditEvent as BaseAudit
from src.erp.base.service import Service as BaseService
from src.erp.base.store import Store as BaseStore
from src.erp.projects.dependencies import Dependencies
from src.erp.projects.metatables import AuditEvent, DeliveryTask, Project, TimeEntry
from src.erp.projects.service import Service
from src.erp.projects.store import Store, require_local_runtime


@pytest.fixture(scope="session")
def project_services():
    configure_local_client()
    expected = os.environ.get("PROJECTS_LOCAL_SOURCE_UID")
    assert expected and str(require_local_runtime()) == expected
    upgrade_application("src.erp.projects.migrations:migration")
    actor = User.get_authenticated_user_details().uid
    base = BaseService(
        BaseStore(local_only=True), actor, {"base.read", "base.write", "base.configure"}
    )
    svc = Service(
        Store(local_only=True),
        actor,
        {"projects.read", "projects.write", "projects.manage", "projects.configure"},
        Dependencies(base),
    )
    return svc, base


@pytest.fixture
def business(project_services):
    svc, base = project_services
    owned = []
    projects = []

    def create(resource, **values):
        row = base.save(resource, {"name": "Project fixture " + uuid4().hex[:8], **values})
        owned.append((resource, UUID(row["uid"])))
        return row

    currency = base.collection("currencies", search="EUR")["items"][0]
    party = create("parties", kind="organization")
    person = create("parties", kind="person")
    issuer = create("parties", kind="organization")
    company = create("operating-companies", party_uid=issuer["uid"], currency_uid=currency["uid"])
    payload = {
        "name": "Project " + uuid4().hex[:12],
        "customer_uid": party["uid"],
        "operating_company_uid": company["uid"],
    }

    def new(**changes):
        uid = uuid4()
        projects.append(uid)
        return svc.save_project(
            {**payload, "name": "Project " + uuid4().hex[:12], **changes}, request_uid=uid
        )

    def task(project, **changes):
        return svc.save_task(
            {
                "name": "Deliver service",
                "project_uid": project["uid"],
                "assignee_party_uid": person["uid"],
                **changes,
            },
            expected_project_version=project["version"],
            request_uid=uuid4(),
        )

    yield {
        "service": svc,
        "base": base,
        "new": new,
        "task": task,
        "payload": payload,
        "projects": projects,
        "party": party,
        "person": person,
        "company": company,
    }
    for uid in projects:
        tasks = svc.store.read(select(DeliveryTask.uid).where(DeliveryTask.project_uid == uid))
        ids = [UUID(row["uid"]) for row in tasks]
        entries = (
            svc.store.read(select(TimeEntry.uid).where(TimeEntry.task_uid.in_(ids))) if ids else []
        )
        audit_ids = [uid, *ids, *[UUID(row["uid"]) for row in entries]]
        svc.store.write(
            [
                delete(AuditEvent).where(AuditEvent.record_uid.in_(audit_ids)),
                delete(TimeEntry).where(TimeEntry.task_uid.in_(ids)),
                delete(DeliveryTask).where(DeliveryTask.project_uid == uid),
                delete(Project).where(Project.uid == uid),
            ]
        )
    for resource, uid in reversed(owned):
        base.store.write(
            [
                delete(BaseAudit).where(BaseAudit.record_uid == uid),
                delete(BASE[resource]).where(BASE[resource].uid == uid),
            ]
        )
