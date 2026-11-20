"""Resolve and mutate User Preferences through the governed SQL interface."""

from functools import cached_property, lru_cache
from uuid import UUID

from metatables import MetaTable
from metatables.compiled_sql.v1 import compile_sqlalchemy_statement, compile_sqlalchemy_statements

from .errors import UserPreferencesError
from .metatables import (
    ADMISSION_MODELS,
    MODELS,
    OWNER_NAMESPACE,
)
from .scope import configured_source, require_local_runtime


class Store:
    def __init__(self, source_uid: UUID, *, local=False, policy_only=False):
        self.source_uid = source_uid
        self.local = local
        self.binding_models = ADMISSION_MODELS if policy_only else MODELS

    @cached_property
    def data_source_uid(self):
        expected = {model.__metatable_identifier__: model for model in self.binding_models}
        rows = MetaTable.filter(identifier__in=list(expected), provisioning_status="active")
        if (
            len(rows) != len(expected)
            or {row.identifier for row in rows} != set(expected)
            or any(not self._matches_binding(row, expected[row.identifier]) for row in rows)
        ):
            raise UserPreferencesError(
                503, "module_policy_unavailable", "User Preferences catalog bindings are not ready"
            )
        return self.source_uid

    def _matches_binding(self, row, model):
        expected_namespaces = {OWNER_NAMESPACE, *getattr(model, "__metatable_namespaces__", ())}
        return (
            row.physical_table_name == model.__tablename__
            and row.physical_schema in (None, "", "public")
            and row.management_mode == "platform_managed"
            and row.schema_management_mode == "alembic_managed"
            and row.migration_namespace == OWNER_NAMESPACE
            and expected_namespaces <= {namespace.name for namespace in row.namespaces}
            and row.migration_provider_key == f"src.erp.user_preferences:{OWNER_NAMESPACE}"
            and row.alembic_revision in {"0001", "0002", "0003"}
            and str(row.data_source_uid) == str(self.source_uid)
        )

    def rows(self, statement, *, limit):
        return MetaTable.execute_operation(
            compile_sqlalchemy_statement(
                statement.limit(limit),
                operation="select",
                data_source_uid=self.data_source_uid,
                limits={"max_rows": limit, "statement_timeout_ms": 10000},
            )
        )["rows"]
    def one(self, statement):
        rows = self.rows(statement, limit=1)
        return rows[0] if rows else None

    def write(self, statements):
        if self.local and require_local_runtime() != self.data_source_uid:
            raise UserPreferencesError(
                503, "module_policy_unavailable", "User Preferences local DataSource changed"
            )
        return MetaTable.execute_transaction(
            compile_sqlalchemy_statements(
                statements,
                operation="update",
                data_source_uid=self.data_source_uid,
                limits={"max_rows": 100, "statement_timeout_ms": 10000},
            )
        )


@lru_cache(maxsize=8)
def _store(source_uid, local, policy_only):
    return Store(source_uid, local=local, policy_only=policy_only)


def configured_store(*, local=False, policy_only=False):
    return _store(configured_source(local=local), local, policy_only)
