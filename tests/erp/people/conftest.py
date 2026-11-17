import os
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from mainsequence.client import User
from metatables import configure_local_client, upgrade_application
from src.erp.base.metatables import RESOURCES as BASE
from src.erp.base.metatables import AuditEvent as BaseAudit
from src.erp.base.service import Service as BaseService
from src.erp.base.store import Store as BaseStore
from src.erp.people.dependencies import Dependencies
from src.erp.people.metatables import RESOURCES, AuditEvent
from src.erp.people.service import Service
from src.erp.people.store import Store, require_local_runtime


@pytest.fixture(scope="session")
def people_services():
    configure_local_client()
    expected = os.environ.get("PEOPLE_LOCAL_SOURCE_UID")
    assert expected and str(require_local_runtime()) == expected
    upgrade_application("src.erp.people.migrations:migration")
    actor = User.get_authenticated_user_details().uid
    base = BaseService(
        BaseStore(local_only=True), actor, {"base.read", "base.write", "base.configure"}
    )
    svc = Service(
        Store(local_only=True),
        actor,
        {"people.read", "people.write", "people.manage", "people.configure"},
        Dependencies(base),
    )
    return svc, base


@pytest.fixture
def workforce(people_services):
    svc, base = people_services
    owned, records = [], []

    def base_create(resource, **values):
        row = base.save(resource, {"name": "People fixture " + uuid4().hex[:8], **values})
        owned.append((resource, UUID(row["uid"])))
        return row

    currency = base.collection("currencies", search="EUR")["items"][0]
    person = base_create("parties", kind="person")
    issuer = base_create("parties", kind="organization")
    company = base_create(
        "operating-companies", party_uid=issuer["uid"], currency_uid=currency["uid"]
    )

    def create(resource, payload, **kwargs):
        uid = uuid4()
        records.append((resource, uid))
        return getattr(
            svc,
            {
                "departments": "save_department",
                "employees": "save_employee",
                "absences": "save_absence",
            }[resource],
        )(payload, request_uid=uid, **kwargs)

    def department(**changes):
        return create(
            "departments",
            {
                "name": "Delivery " + uuid4().hex[:8],
                "operating_company_uid": company["uid"],
                **changes,
            },
        )

    def employee(**changes):
        return create(
            "employees",
            {
                "person_uid": person["uid"],
                "operating_company_uid": company["uid"],
                "start_date": date.today() - timedelta(days=365),
                "job_title": "Consultant",
                **changes,
            },
        )

    def absence(emp, **changes):
        return create(
            "absences",
            {
                "name": "Planned time off",
                "employee_uid": emp["uid"],
                "start_date": date.today() + timedelta(days=10),
                "end_date": date.today() + timedelta(days=12),
                **changes,
            },
            expected_employee_version=emp["version"],
        )

    yield {
        "service": svc,
        "base": base,
        "base_create": base_create,
        "person": person,
        "company": company,
        "issuer": issuer,
        "department": department,
        "employee": employee,
        "absence": absence,
        "records": records,
    }
    for resource in ["absences", "employees", "departments"]:
        ids = [uid for kind, uid in records if kind == resource]
        if ids:
            svc.store.write(
                [
                    delete(AuditEvent).where(AuditEvent.record_uid.in_(ids)),
                    delete(RESOURCES[resource]).where(RESOURCES[resource].uid.in_(ids)),
                ]
            )
    for resource, uid in reversed(owned):
        base.store.write(
            [
                delete(BaseAudit).where(BaseAudit.record_uid == uid),
                delete(BASE[resource]).where(BASE[resource].uid == uid),
            ]
        )
