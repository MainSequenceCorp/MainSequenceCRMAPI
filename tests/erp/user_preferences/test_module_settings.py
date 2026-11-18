import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select, update

from api.erp.user_preferences.main import ready_modules
from metatables import MetaTable, MetaTableTransactionGuardError, configure_local_client
from src.erp.modules import MODULES
from src.erp.user_preferences.admission import POLICY_LABEL, guard_active, require_active
from src.erp.user_preferences.errors import UserPreferencesError
from src.erp.user_preferences.metatables import (
    ADMISSION_MODELS,
    MODELS,
    OWNER_NAMESPACE,
    ModuleActivationChange,
    ModuleAdmissionLock,
)
from src.erp.user_preferences.schemas import ActivationInput, ActivationProposal, PreferenceInput
from src.erp.user_preferences.scope import MODULES_SETTING, SOURCE_SETTING, configured_source
from src.erp.user_preferences.service import Service, preview_target
from src.erp.user_preferences.store import Store, configured_store


def test_manufacturing_requires_catalog_and_inventory_and_blocks_their_removal():
    provisioned = MODULES.keys()
    added = preview_target([], ["manufacturing"], provisioned)
    assert not added["valid"]
    assert set(added["required_module_keys"]) == {"catalog", "inventory"}
    assert "base" not in added["required_module_keys"]

    removed = preview_target(
        ["catalog", "inventory", "manufacturing"], ["catalog", "manufacturing"], provisioned
    )
    assert removed["blockers"] == [
        {
            "code": "active_dependent",
            "module_key": "inventory",
            "related_module_keys": ["manufacturing"],
        }
    ]
    assert preview_target([], ["catalog", "inventory", "manufacturing"], provisioned)["valid"]


def test_optional_workflows_do_not_block_the_consumer_and_report_changes():
    target = ["finance", "catalog"]
    proposal = preview_target(["finance", "catalog", "sales"], target, MODULES.keys())
    invoicing = next(
        effect for effect in proposal["affected_features"] if effect["key"] == "order_to_invoice"
    )
    assert proposal["valid"]
    assert not invoicing["available_after"]
    assert any(
        blocker["code"] == "module_unavailable" and blocker["module_key"] == "catalog"
        for blocker in preview_target([], ["catalog", "sales"], {"base", "sales"})["blockers"]
    )


def test_admission_catalog_needs_only_policy_read_and_lock_write_namespaces(monkeypatch):
    source = uuid4()
    requested = []
    rows = [
        SimpleNamespace(
            identifier=model.__metatable_identifier__,
            physical_table_name=model.__tablename__,
            physical_schema=None,
            management_mode="platform_managed",
            schema_management_mode="alembic_managed",
            migration_namespace=OWNER_NAMESPACE,
            migration_provider_key=f"src.erp.user_preferences:{OWNER_NAMESPACE}",
            namespaces=[
                SimpleNamespace(name=namespace)
                for namespace in (OWNER_NAMESPACE, *model.__metatable_namespaces__)
            ],
            alembic_revision="0001",
            data_source_uid=source,
        )
        for model in ADMISSION_MODELS
    ]

    def catalog_filter(*, identifier__in, provisioning_status):
        assert provisioning_status == "active"
        requested.extend(identifier__in)
        return rows

    monkeypatch.setattr(MetaTable, "filter", catalog_filter)
    assert Store(source, policy_only=True).data_source_uid == source
    assert set(requested) == {model.__metatable_identifier__ for model in ADMISSION_MODELS}
    assert {row.namespaces[1].name for row in rows} == {"erp-module-policy", "erp-module-admission"}

    rows[0].namespaces.pop()
    with pytest.raises(UserPreferencesError, match="catalog bindings"):
        _ = Store(source, policy_only=True).data_source_uid


@pytest.mark.parametrize(
    "payload",
    [
        {"hidden_module_keys": ["base"], "expected_version": 0},
        {"hidden_module_keys": ["unknown"], "expected_version": 0},
        {"hidden_module_keys": ["crm", "crm"], "expected_version": 0},
        {"hidden_module_keys": ["crm"], "expected_version": 0, "person_uid": str(uuid4())},
    ],
)
def test_personal_contract_accepts_only_unique_optional_keys_for_current_person(payload):
    with pytest.raises(ValidationError):
        PreferenceInput.model_validate(payload)
    with pytest.raises(ValidationError):
        ActivationProposal(active_module_keys=["base"], expected_version=1)


@pytest.fixture
def local_scope(monkeypatch):
    expected = os.environ.get("ERP_USER_PREFERENCES_TEST_SOURCE_UID")
    if not expected:
        pytest.skip("Set ERP_USER_PREFERENCES_TEST_SOURCE_UID to the verified local DataSource")
    configure_local_client()
    monkeypatch.setenv(SOURCE_SETTING, expected)
    monkeypatch.setenv(MODULES_SETTING, ",".join(MODULES))
    assert configured_source(local=True) == UUID(expected)
    scope = uuid4()
    store = configured_store(local=True)
    manager = Service(store, scope, uuid4(), can_manage=True)
    try:
        yield manager, store, scope
    finally:
        store.write(
            [
                delete(model.__table__).where(model.environment_uid == scope)
                for model in reversed(MODELS)
            ]
        )


@pytest.fixture
def local_policy(local_scope):
    manager, _, _ = local_scope
    manager.seed(["catalog", "sales"], MODULES.keys())
    return local_scope


def test_readiness_batches_module_lookups_and_revalidates_bindings(local_scope, monkeypatch):
    _, store, _ = local_scope
    assert store.data_source_uid == store.source_uid
    original_filter = MetaTable.filter
    batches = []
    reject_sales_binding = False

    def catalog_filter(*, identifier__in, provisioning_status):
        batches.append(tuple(identifier__in))
        rows = original_filter(identifier__in=identifier__in, provisioning_status=provisioning_status)
        if reject_sales_binding:
            return [row for row in rows if row.identifier != "erp_sales.order"]
        return rows

    monkeypatch.setattr(MetaTable, "filter", catalog_filter)
    assert ready_modules(store, local=True) == MODULES.keys()
    assert len(batches) == 2
    assert not set(batches[0]) & set(batches[1])

    reject_sales_binding = True
    assert ready_modules(store, local=True) == MODULES.keys() - {"sales"}
    assert len(batches) == 4


def test_first_policy_save_is_admin_only_audited_and_idempotent(local_scope):
    manager, store, scope = local_scope
    provisioned = MODULES.keys()
    initial = ActivationInput(
        active_module_keys=["catalog", "sales"], expected_version=0, request_uid=uuid4()
    )
    assert manager.administrator_policy() == {"active_module_keys": [], "version": 0}
    with pytest.raises(UserPreferencesError) as missing:
        require_active(scope, ["base"], local=True)
    assert missing.value.status == 503
    reader = Service(store, scope, uuid4(), can_manage=False)
    with pytest.raises(UserPreferencesError) as unauthorized:
        reader.save_activation(initial, provisioned)
    assert unauthorized.value.status == 403
    incomplete = ActivationInput(
        active_module_keys=["sales"], expected_version=0, request_uid=uuid4()
    )
    assert not manager.preflight(incomplete, provisioned)["valid"]
    with pytest.raises(UserPreferencesError) as invalid:
        manager.save_activation(incomplete, provisioned)
    assert invalid.value.code == "invalid_module_set"
    assert manager.administrator_policy()["version"] == 0

    assert manager.preflight(initial, provisioned)["valid"]
    assert manager.save_activation(initial, provisioned)["version"] == 1
    assert manager.save_activation(initial, provisioned)["version"] == 1
    assert require_active(scope, ["sales", "base"], local=True)["version"] == 1
    audit = ModuleActivationChange.__table__
    event = store.one(select(audit).where(audit.c.environment_uid == scope))
    assert event["request_uid"] == str(initial.request_uid)
    assert event["previous_module_keys"] == []
    assert event["active_module_keys"] == ["catalog", "sales"]
    another = ActivationInput(active_module_keys=[], expected_version=0, request_uid=uuid4())
    with pytest.raises(UserPreferencesError) as version:
        manager.save_activation(another, provisioned)
    assert version.value.code == "version_conflict"


def test_local_personal_preference_and_manager_permissions(local_policy):
    manager, store, scope = local_policy
    reader = Service(store, scope, uuid4(), can_manage=False)
    assert reader.preferences() == {"version": 0, "hidden_module_keys": []}
    change = PreferenceInput(hidden_module_keys=["sales"], expected_version=0)
    assert reader.save_preferences(change) == {"version": 1, "hidden_module_keys": ["sales"]}
    assert manager.preferences() == {"version": 0, "hidden_module_keys": []}
    reader_bootstrap = reader.bootstrap(MODULES.keys(), lambda key: key != "sales")
    manager_bootstrap = manager.bootstrap(MODULES.keys(), lambda key: key != "sales")
    assert reader_bootstrap["active_module_keys"] == ["catalog", "sales"]
    assert reader_bootstrap["policy_version"] == 1
    assert reader_bootstrap["preferences"] == {"version": 1, "hidden_module_keys": ["sales"]}
    assert manager_bootstrap["preferences"] == {"version": 0, "hidden_module_keys": []}
    assert not next(row for row in reader_bootstrap["modules"] if row["key"] == "sales")["can_access"]
    with pytest.raises(UserPreferencesError, match="Settings changed"):
        reader.save_preferences(change)
    with pytest.raises(UserPreferencesError, match="Only an ERP administrator"):
        reader.preflight(
            ActivationProposal(active_module_keys=[], expected_version=1), MODULES.keys()
        )
    assert require_active(scope, ["sales", "base"], local=True)["version"] == 1


def test_local_deactivation_rolls_back_a_previously_admitted_write(local_policy):
    manager, store, scope = local_policy
    old = require_active(scope, ["sales"], local=True)["version"]
    guard = guard_active(scope, ["sales"], store.data_source_uid, local=True, policy_version=old)
    locked = ModuleAdmissionLock.__table__
    mutation = update(locked).where(locked.c.environment_uid == scope).values(lock_marker=7)
    change = ActivationInput(
        active_module_keys=["catalog"], expected_version=old, request_uid=uuid4()
    )
    saved = manager.save_activation(change, MODULES.keys())
    assert saved["version"] == old + 1
    assert manager.save_activation(change, MODULES.keys())["version"] == old + 1

    with pytest.raises(MetaTableTransactionGuardError) as failed:
        store.write([*guard, mutation])
    assert failed.value.label == POLICY_LABEL
    row = store.one(select(locked).where(locked.c.environment_uid == scope))
    assert row["lock_marker"] == 0
    with pytest.raises(UserPreferencesError) as denied:
        require_active(scope, ["sales"], local=True)
    assert denied.value.status == 403
    assert denied.value.code == "module_disabled"
