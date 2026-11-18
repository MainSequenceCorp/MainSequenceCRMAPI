"""Only a backend-advertised active CRM release may replace the frontend binding."""

import runpy
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

script = runpy.run_path(str(Path(__file__).resolve().parents[4] / "scripts/erp/crm/bind_crm_frontend.py"))
active_binding, bind_workflow = script["active_binding"], script["bind_workflow"]

BRANCH, ENVIRONMENT, RELEASE, REVISION = [str(uuid.UUID(int=n)) for n in range(800, 804)]


def candidate():
    return SimpleNamespace(
        uid=RELEASE, name="crm", release_kind="fastapi", code_repository_branch_uid=BRANCH,
        active_revision=REVISION, mcp_enabled=True,
        mcp_connection=SimpleNamespace(
            url="https://issued-by-platform.example.test/mcp", transport="streamable-http",
            active_revision_uid=REVISION, organization_environment_uid=ENVIRONMENT,
        ),
    )


def context():
    return SimpleNamespace(code_repository_branch_uid=BRANCH, organization_environment_uid=ENVIRONMENT)


@pytest.mark.parametrize("invalid", ["inactive", "wrong_branch", "wrong_environment", "wrong_revision", "old_non_mcp", "unsafe_url"])
def test_binding_rejects_unready_or_unrelated_backend_releases(invalid):
    release = candidate()
    if invalid == "inactive":
        release.active_revision = None
    elif invalid == "wrong_branch":
        release.code_repository_branch_uid = str(uuid.UUID(int=900))
    elif invalid == "wrong_environment":
        release.mcp_connection.organization_environment_uid = str(uuid.UUID(int=901))
    elif invalid == "wrong_revision":
        release.mcp_connection.active_revision_uid = str(uuid.UUID(int=902))
    elif invalid == "old_non_mcp":
        release.mcp_enabled = False
    else:
        release.mcp_connection.url = "https://user:password@example.test/mcp"
    with pytest.raises(RuntimeError):
        active_binding(context(), [release])


@pytest.mark.parametrize("binding_key", ["VITE_CRM_FASTAPI_RELEASE_UID", "VITE_ERP_FASTAPI_RELEASE_UID"])
def test_pinned_binding_preserves_workflow_and_is_idempotent(tmp_path, binding_key):
    binding = active_binding(context(), [candidate()])
    path = tmp_path / "crm-site.yaml"
    original = (
        "# keep the one workflow\nname: crm\nbuild_environment:\n"
        f"  {binding_key}: old\nother: unchanged\n"
    )
    path.write_text(original)
    assert bind_workflow(path, binding, apply=False)
    assert path.read_text() == original
    assert bind_workflow(path, binding, apply=True)
    assert path.read_text() == original.replace(": old", f": {RELEASE}")
    assert not bind_workflow(path, binding, apply=True)


def test_named_erp_api_binding_is_preserved(tmp_path):
    path = tmp_path / "crm-site.yaml"
    original = """resources:
  - key: crm-site
    spec:
      build_environment:
        VITE_ERP_FASTAPI_RELEASE_UID:
          resource_release:
            repository: MainSequenceCRMAPI
            key: crm
"""
    path.write_text(original)
    assert bind_workflow(path, active_binding(context(), [candidate()]), apply=True) is False
    assert path.read_text() == original
