from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.erp.main import create_app
from api.erp.user_preferences import main as settings_api
from mainsequence.client import User
from mainsequence.server import fastapi as identity

ASSERTION = {"X-MainSequence-Caller-Assertion": "fixture"}


@pytest.fixture
def hosted_caller(monkeypatch):
    caller = SimpleNamespace(
        user_uid=str(uuid4()),
        is_organization_admin=False,
        release_uid=str(uuid4()),
        environment_uid=str(uuid4()),
        _requester=None,
    )

    def verify(assertion):
        assert assertion == "fixture"
        return caller

    monkeypatch.setenv("MAINSEQUENCE_CALLER_AUTH_MODE", "assertion")
    monkeypatch.setenv("MAINSEQUENCE_ORGANIZATION_ENVIRONMENT_UID", caller.environment_uid)
    monkeypatch.setattr(
        identity.CallerAssertionVerifier,
        "from_environment",
        lambda: SimpleNamespace(verify=verify),
    )
    return caller


@pytest.mark.parametrize(
    ("profile_type", "filter_match", "status"),
    [
        (None, "exact", 200),
        (None, "different", 403),
        (None, "inactive", 403),
        (None, "workload", 403),
        ("workload", "unused", 403),
    ],
)
def test_hosted_bootstrap_requires_exact_active_human_proof(
    monkeypatch, hosted_caller, profile_type, filter_match, status
):
    actor = hosted_caller.user_uid
    calls = []

    def profile(uid):
        assert uid == actor
        return SimpleNamespace(
            uid=uid, is_active=True, identity_type=profile_type, is_organization_admin=True
        )

    def filtered(*, uid, identity_type):
        assert uid == actor and identity_type == "human"
        calls.append(uid)
        return [SimpleNamespace(
            uid=str(uuid4()) if filter_match == "different" else uid,
            is_active=filter_match != "inactive",
            identity_type="workload" if filter_match == "workload" else None,
        )]

    monkeypatch.setattr(User, "get_by_uid", profile)
    monkeypatch.setattr(User, "filter", filtered)
    monkeypatch.setattr(settings_api, "configured_store", lambda **kwargs: object())
    monkeypatch.setattr(settings_api, "ready_modules", lambda *args, **kwargs: frozenset())
    monkeypatch.setattr(
        settings_api.Service,
        "bootstrap",
        lambda self, *_: {"actor": str(self.actor), "can_manage": self.can_manage},
    )

    with TestClient(create_app(), headers=ASSERTION) as client:
        response = client.get("/api/erp/v1/bootstrap/")

    assert response.status_code == status
    assert calls == ([actor] if profile_type is None else [])
    if status == 200:
        assert response.json() == {"actor": actor, "can_manage": False}
    else:
        assert response.json()["error"]["code"] == "person_required"
