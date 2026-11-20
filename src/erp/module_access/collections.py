"""Activation decisions for collections that read policy and rows together."""

from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import (
    String,
    and_,
    case,
    cast,
    false,
    func,
    literal,
    literal_column,
    not_,
    or_,
    select,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB

from src.erp.modules import MODULES, OPTIONAL_MODULES, REQUIRED_MODULES, module_closure
from src.erp.user_preferences.errors import UserPreferencesError


@dataclass
class CollectionAdmission:
    module_key: str
    scope: UUID
    local: bool
    checked: bool = False
    data_ms: float | None = None

    def decision(self, source_uid):
        from src.erp.user_preferences.metatables import EnvironmentModuleActivation
        from src.erp.user_preferences.scope import provisioned_module_keys
        from src.erp.user_preferences.store import configured_store

        policy_store = configured_store(local=self.local, policy_only=True)
        if UUID(str(source_uid)) != policy_store.data_source_uid:
            raise UserPreferencesError(
                503,
                "module_policy_source_mismatch",
                "ERP module policy and collection must share the governed DataSource",
            )
        provisioned = provisioned_module_keys()
        model = EnvironmentModuleActivation.__table__
        policy = (
            select(model.c.version, model.c.active_module_keys)
            .where(model.c.environment_uid == self.scope)
            .cte("erp_collection_policy")
        )
        array, keys = _policy_members(policy, local=self.local)
        present = select(keys.c.module_key)
        unknown = (
            select(keys.c.module_key)
            .where(or_(not_(keys.c.is_string), keys.c.module_key.not_in(sorted(OPTIONAL_MODULES))))
            .exists()
        )
        distinct = (
            select(func.count() == func.count(keys.c.module_key.distinct()))
            .select_from(keys)
            .scalar_subquery()
        )

        def enabled(module_key):
            if module_key in REQUIRED_MODULES:
                return true()
            return present.where(keys.c.module_key == module_key).exists()

        dependencies = [
            or_(not_(enabled(key)), and_(*(enabled(dep) for dep in module.prerequisites)))
            for key, module in MODULES.items()
            if key in OPTIONAL_MODULES and module.prerequisites
        ]
        valid = (
            select(and_(policy.c.version > 0, array, not_(unknown), distinct, *dependencies))
            .select_from(policy)
            .scalar_subquery()
        )
        required = module_closure((self.module_key,))
        admitted = (
            and_(*(enabled(key) for key in sorted(required)))
            if required <= provisioned
            else false()
        )
        return select(
            case(
                (not_(func.coalesce(valid, false())), "unavailable"),
                (admitted, "allowed"),
                else_="disabled",
            ).label("_erp_policy_state")
        ).cte("erp_collection_decision")

    def verify(self, state):
        self.checked = True
        if state == "disabled":
            raise UserPreferencesError(403, "module_disabled", "A required ERP module is inactive")
        if state != "allowed":
            raise UserPreferencesError(
                503, "module_policy_unavailable", "ERP module policy is unavailable"
            )


def _policy_members(policy, *, local):
    raw = policy.c.active_module_keys
    if local:
        array = case((func.json_valid(raw) == 1, func.json_type(raw) == "array"), else_=false())
        document = case((array, raw), else_="[]")
        length = func.json_array_length(document)
        positions = (
            select(literal(0).label("position"))
            .union_all(*(select(literal(position)) for position in range(1, len(OPTIONAL_MODULES))))
            .cte("erp_collection_key_positions")
        )
        path = literal("$[") + cast(positions.c.position, String) + literal("]")
        keys = select(
            func.json_extract(document, path).label("module_key"),
            (func.json_type(document, path) == "text").label("is_string"),
        ).select_from(policy.join(positions, positions.c.position < length))
        return and_(array, length <= len(OPTIONAL_MODULES)), keys.cte("erp_collection_active_keys")
    document = cast(raw, JSONB)
    array = func.jsonb_typeof(document) == "array"
    table = func.jsonb_array_elements(
        case((array, document), else_=cast(literal_column("'[]'"), JSONB))
    ).table_valued("value")
    keys = select(
        table.c.value.op("#>>")(literal_column("'{}'")).label("module_key"),
        (func.jsonb_typeof(table.c.value) == "string").label("is_string"),
    ).select_from(policy.join(table, true()))
    return array, keys.cte("erp_collection_active_keys")


collection_admission: ContextVar[CollectionAdmission | None] = ContextVar(
    "erp_collection_admission", default=None
)
