"""The common workflow reconciles provisioned ERP schemas before deployment."""

from __future__ import annotations

import runpy
from pathlib import Path
from uuid import UUID

import pytest
import yaml
from jobs.erp.crm.migrate import migration_providers

import metatables
from src.erp.modules import MODULES, resolve_modules

ROOT = Path(__file__).resolve().parents[4]
WORKFLOWS = ROOT / ".mainsequence" / "workflows"
RUNTIME_TAG_POLICY = {"enabled": True, "tag_regex": r"^v[0-9]+[.][0-9]+[.][0-9]+-erp-api$"}
SOURCE = str(UUID(int=18249))
BASE_CRM_PROVIDERS = (
    "src.erp.base.migrations:migration",
    "src.erp.crm.migrations:migration",
    "src.erp.user_preferences.migrations:migration",
)


def _workflow() -> dict:
    return yaml.safe_load((WORKFLOWS / "crm-api.yaml").read_text(encoding="utf-8"))


def _configure_job(monkeypatch, *, source=SOURCE, local_mode=False):
    monkeypatch.setenv("ERP_USER_PREFERENCES_DATA_SOURCE_UID", SOURCE)
    monkeypatch.setenv("ERP_USER_PREFERENCES_PROVISIONED_MODULES", "crm,base")
    monkeypatch.setattr(
        metatables,
        "get_runtime_status",
        lambda: {
            "local_mode": local_mode,
            "bootstrap": {"active": True, "status": "ready"},
            "data_source": {"uid": source},
        },
    )


@pytest.mark.parametrize("migrated,state", [(False, "already current"), (True, "migrated")])
def test_migration_job_upgrades_provisioned_modules_and_preferences(monkeypatch, capsys, migrated, state):
    _configure_job(monkeypatch)
    calls = []

    def upgrade_application(provider):
        calls.append(provider)
        return {"migrated": migrated, "revision": "0009", "data_source_uid": SOURCE}

    monkeypatch.setattr(metatables, "upgrade_application", upgrade_application)
    runpy.run_path(str(ROOT / "jobs" / "migrate_crm.py"), run_name="__main__")
    assert calls == list(BASE_CRM_PROVIDERS)
    assert capsys.readouterr().out.splitlines() == [
        f"{provider}: 0009 ({state}; catalog reconciled) on {SOURCE}"
        for provider in BASE_CRM_PROVIDERS
    ]


def test_migration_job_orders_all_modules_by_prerequisites():
    providers = migration_providers(MODULES)
    assert set(providers) == {
        *(module.migration_provider for module in MODULES.values()),
        "src.erp.user_preferences.migrations:migration",
    }
    assert len(providers) == len(MODULES) + 1
    for module in resolve_modules(MODULES):
        for dependency in module.prerequisites:
            assert providers.index(MODULES[dependency].migration_provider) < providers.index(
                module.migration_provider
            )


@pytest.mark.parametrize("source,local_mode", [(str(UUID(int=1)), False), (SOURCE, True)])
def test_migration_job_blocks_unexpected_runtime_before_writes(monkeypatch, source, local_mode):
    _configure_job(monkeypatch, source=source, local_mode=local_mode)
    monkeypatch.setattr(
        metatables,
        "upgrade_application",
        lambda _provider: pytest.fail("Unexpected migration against an unverified runtime"),
    )
    with pytest.raises(RuntimeError, match="configured hosted DataSource"):
        runpy.run_path(str(ROOT / "jobs" / "erp" / "crm" / "migrate.py"), run_name="__main__")


def test_migration_job_propagates_finalization_failure(monkeypatch, capsys):
    _configure_job(monkeypatch)
    calls = []

    def upgrade_application(provider):
        calls.append(provider)
        raise RuntimeError("physical_table_missing")

    monkeypatch.setattr(metatables, "upgrade_application", upgrade_application)
    with pytest.raises(RuntimeError, match="physical_table_missing"):
        runpy.run_path(str(ROOT / "jobs" / "erp" / "crm" / "migrate.py"), run_name="__main__")
    assert calls == [BASE_CRM_PROVIDERS[0]]
    assert capsys.readouterr().out == ""


def test_the_repository_has_one_workflow_file():
    assert sorted(path.name for path in WORKFLOWS.iterdir()) == ["crm-api.yaml"]


def test_release_tag_promotes_the_shared_api_then_assistant_after_the_migration():
    workflow = _workflow()
    assert (workflow["api_version"], workflow["name"]) == ("3.0.0", "crm-api")
    resources = {item["key"]: item for item in workflow["resources"]}
    assert set(resources) == {"crm", "migrate-crm", "crm-assistant"}

    crm = resources["crm"]["spec"]
    assert crm["source_path"] == "api/crm/main.py"
    assert (ROOT / crm["source_path"]).is_file()
    assert crm["mcp_enabled"] is True
    assert crm["automatic_deployment"] is True
    assert crm["automatic_redeployment"] == RUNTIME_TAG_POLICY
    assert {route["path"] for route in crm["public_ingress"]} == {
        "/extensions/google/oauth/callback/",
        "/extensions/google/oauth/done/",
    }

    job = resources["migrate-crm"]["spec"]
    assert job["execution_path"] == "jobs/migrate_crm.py"
    assert job["automatic_redeployment"] == RUNTIME_TAG_POLICY
    assert job["env_vars"] == crm["env_vars"]
    config = {item["name"]: item["value"] for item in job["env_vars"]}
    UUID(config["ERP_USER_PREFERENCES_DATA_SOURCE_UID"])
    assert set(config["ERP_USER_PREFERENCES_PROVISIONED_MODULES"].split(",")) == set(MODULES)

    assert workflow["execution"] == {
        "steps": {
            "image": {"prepare_image": "crm"},
            "migrate": {"run_job": "migrate-crm", "image_from": "image", "needs": ["image"]},
            "deploy_api": {"deploy": "crm", "image_from": "image", "needs": ["migrate"]},
            "image_assistant": {"prepare_image": "crm-assistant"},
            "deploy_assistant": {
                "deploy": "crm-assistant",
                "image_from": "image_assistant",
                "needs": ["deploy_api", "image_assistant"],
            },
        }
    }


def test_registered_api_requires_erp_settings_in_hosted_mode(monkeypatch):
    from api.erp.main import app
    from src.erp.user_preferences.errors import UserPreferencesError

    entrypoint = ROOT / "api" / "crm" / "main.py"
    monkeypatch.setitem(app.state.mainsequence_request_identity, "mode", "assertion")
    monkeypatch.setenv("MAINSEQUENCE_ORGANIZATION_ENVIRONMENT_UID", str(UUID(int=42)))
    monkeypatch.delenv("ERP_USER_PREFERENCES_DATA_SOURCE_UID", raising=False)
    with pytest.raises(UserPreferencesError):
        runpy.run_path(str(entrypoint))

    monkeypatch.setenv("ERP_USER_PREFERENCES_DATA_SOURCE_UID", SOURCE)
    monkeypatch.setenv("ERP_USER_PREFERENCES_PROVISIONED_MODULES", "base,crm")
    assert runpy.run_path(str(entrypoint))["app"] is app


def test_the_assistant_kept_its_declaration_when_it_moved_into_this_file():
    resources = {item["key"]: item for item in _workflow()["resources"]}
    assert resources["crm-assistant"]["spec"] == {
        "source_path": "api/tau/main.py",
        "mcp_applications": [{"resource": "crm"}],
        "llm_provider": "openai-codex",
        "llm_model": "gpt-5.6-luna",
        "llm_thinking": "medium",
        "command_center_icon": {
            "path": "assets/erp/crm/agent/sequence/assets/crm/neutral/idle.png",
            "rendering": "color",
            "image_rendering": "auto",
        },
        "command_center_animations": {
            "poses": {
                "thinking": {"path": "assets/erp/crm/agent/sequence/assets/crm/neutral/thinking.png"},
                "working": {"path": "assets/erp/crm/agent/sequence/assets/crm/neutral/working.png"},
                "outreach": {"path": "assets/erp/crm/agent/sequence/assets/crm/neutral/working.png"},
                "error": {"path": "assets/erp/crm/agent/sequence/assets/crm/neutral/error.png"},
            },
            "tools": [{"application": "crm", "pose": "outreach"}],
        },
        "automatic_deployment": True,
        "automatic_redeployment": RUNTIME_TAG_POLICY,
        "revision_retention_count": 3,
        "env_vars": [
            {"name": "TAU_EXCLUDE_BASE_TOOLS", "value": "true"},
            {"name": "TAU_EXCLUDE_MAINSEQUENCE_MCP", "value": "true"},
        ],
    }
