import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from mainsequence.client import User
from mainsequence.server import fastapi as identity
from src.erp.module_access import (
    Admission,
    admission,
    guard_write,
    module_available,
    require_module,
)
from src.erp.module_access.http import install_module_admission
from src.erp.user_preferences.errors import UserPreferencesError


def test_http_admission_follows_sdk_authentication_and_blocks_owner_access(monkeypatch):
    scope = uuid4()
    user = identity.RequestUserIdentity(uid=str(uuid4()), is_organization_admin=True)
    calls = []
    monkeypatch.setenv("MAINSEQUENCE_ENDPOINT", "https://fixture.invalid")
    monkeypatch.setenv("ERP_USER_PREFERENCES_DATA_SOURCE_UID", str(scope))
    monkeypatch.setenv("ERP_USER_PREFERENCES_PROVISIONED_MODULES", "base,finance,sales")
    monkeypatch.setattr(identity, "_users_me", lambda endpoint, token: user)

    async def inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(identity.asyncio, "to_thread", inline)
    monkeypatch.setattr("src.erp.module_access.http.run_in_threadpool", inline)

    def read(scope_uid, keys, *, local):
        assert scope_uid == scope and local
        assert User.get_logged_user().uid == user.uid
        calls.append(tuple(keys))
        return {"version": 4, "active_module_keys": ["finance", "sales"]}

    monkeypatch.setattr("src.erp.user_preferences.admission.require_active", read)
    app = FastAPI()

    @app.get("/business/{owner}")
    async def business(owner: str):
        assert module_available("finance")
        require_module(owner)
        return {"access": "allowed"}

    install_module_admission(app, "finance")
    identity.install_request_identity(app)

    async def verify():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://fixture.invalid") as client:
            assert (await client.get("/business/finance")).status_code == 401
            assert not calls
            headers = {"Authorization": "Bearer fixture"}
            assert (await client.get("/business/finance", headers=headers)).status_code == 200
            denied = await client.get("/business/sales", headers=headers)
            assert denied.status_code == 403
            assert denied.json()["error"]["code"] == "module_disabled"
            assert calls == [("finance",), ("finance",)]

    asyncio.run(verify())


def test_write_guard_uses_module_closure_and_admitted_version(monkeypatch):
    scope, source = uuid4(), uuid4()
    guard, business = object(), object()
    context = Admission(scope, True, 7, frozenset({"base", "catalog", "finance", "sales"}))

    def check(scope_uid, keys, source_uid, *, local, policy_version):
        assert scope_uid == scope and source_uid == source and local
        assert set(keys) == {"base", "catalog", "finance", "sales"}
        assert policy_version == 7
        return [guard]

    monkeypatch.setattr("src.erp.user_preferences.admission.guard_active", check)
    token = admission.set(context)
    try:
        require_module("sales")
        assert guard_write("finance", source, [business]) == [guard, business]
        with pytest.raises(UserPreferencesError) as disabled:
            require_module("inventory")
        assert disabled.value.code == "module_disabled"
    finally:
        admission.reset(token)
