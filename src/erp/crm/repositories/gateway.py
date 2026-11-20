"""Shared, provider-bound Main Sequence MetaTable operation gateway."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from metatables import MetaTable
from metatables.compiled_sql.v1 import compile_sqlalchemy_statement, compile_sqlalchemy_statements
from metatables.models import MetaTableTransactionStatement
from sqlalchemy import select
from src.erp.module_access import admitted_guards, execute_write
from src.erp.module_access.collections import collection_admission

from ..platform.catalog import CatalogRegistry, configured_registry
from ..platform.diagnostics import observe_stage


class GovernedGateway:
    def __init__(self, registry: CatalogRegistry | None = None):
        self.registry = registry or configured_registry()

    @property
    def data_source_uid(self):
        return self.registry.data_source_uid

    def read(self, statement, *, max_rows=100):
        operation = compile_sqlalchemy_statement(
            statement,
            operation="select",
            data_source_uid=self.data_source_uid,
            limits={"max_rows": max_rows, "statement_timeout_ms": 15000},
        )
        return MetaTable.execute_operation(operation)["rows"]

    def _operation(
        self,
        *,
        operation: str,
        sql: str,
        parameters: dict[str, Any],
        parameter_types: dict[str, str],
        max_rows: int = 1000,
        compiled_types: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        with observe_stage(
            "catalog", cache_hit="bindings" in getattr(self.registry, "__dict__", {})
        ):
            data_source_uid = self.registry.data_source_uid
        statement = {
            "sql": sql,
            "parameters": parameters,
            # Existing statements explicitly cast scalar inputs.
            "parameter_types": {
                **{key: value for key, value in parameter_types.items() if value in {"json", "jsonb"}},
                **(compiled_types or {}),
            },
        }
        limits = {"max_rows": max_rows, "statement_timeout_ms": 15000}
        with observe_stage("metatables"):
            if operation != "select":
                guards = admitted_guards("crm", data_source_uid)
                if guards:
                    transaction = compile_sqlalchemy_statements(
                        guards,
                        operation=operation,
                        data_source_uid=data_source_uid,
                        limits=limits,
                    )
                    # Preserve the existing write's result as the final statement.
                    transaction.statements.append(MetaTableTransactionStatement(**statement))
                    return execute_write(transaction)
            return MetaTable.execute_operation(
                {
                    "operation": operation,
                    "statement": statement,
                    "data_source_uid": data_source_uid,
                    "limits": limits,
                }
            )

    def _collection_operation(self, sql, parameters, parameter_types):
        """Admit a legacy PostgreSQL one-row collection in its existing statement."""
        pending = collection_admission.get()
        if pending is None:
            return self._operation(
                operation="select", sql=sql, parameters=parameters,
                parameter_types=parameter_types, max_rows=1,
            )
        source = str(self.registry.data_source_uid)
        decision = pending.decision(source)
        operation = compile_sqlalchemy_statement(
            select(decision.c._erp_policy_state),
            operation="select",
            data_source_uid=source,
            dialect="postgresql",
            paramstyle="pyformat",
        )
        guard = operation.statement
        if parameters.keys() & guard.parameters.keys():
            raise RuntimeError("CRM collection and admission parameter names overlap")
        started = perf_counter()
        result = self._operation(
            operation="select",
            sql=(
                f"WITH erp_admission AS ({guard.sql}) "
                "SELECT _erp_policy_state, CASE WHEN _erp_policy_state='allowed' THEN "
                f"(SELECT to_jsonb(erp_payload) FROM ({sql}) AS erp_payload) "
                "END AS payload FROM erp_admission"
            ),
            parameters={**parameters, **guard.parameters},
            parameter_types=parameter_types,
            compiled_types=guard.parameter_types,
            max_rows=1,
        )
        pending.data_ms = (perf_counter() - started) * 1000
        rows = result.get("rows")
        if not isinstance(rows, list) or len(rows) != 1:
            raise RuntimeError("Invalid guarded CRM collection response")
        pending.verify(rows[0]["_erp_policy_state"])
        return {"rows": [self._json(rows[0]["payload"], expected=dict, label="collection")]}

    @staticmethod
    def _json(value: Any, *, expected: type, label: str) -> Any:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"CRM {label} response is invalid JSON") from exc
        if not isinstance(value, expected):
            raise RuntimeError(f"CRM {label} response has an invalid shape")
        return value

    @staticmethod
    def _parameter(name: str, value: Any) -> tuple[Any, str, str]:
        json_fields = {
            "emails",
            "phones",
            "context_links",
            "logo_ref",
            "avatar_ref",
            "socials",
            "attachment_refs",
            "changes",
        }
        uuid_fields = {
            "owner_uid",
            "company_uid",
            "pipeline_uid",
            "stage_uid",
            "contact_uid",
            "deal_uid",
            "author_uid",
            "completed_by_uid",
            "created_by_uid",
            "updated_by_uid",
        }
        timestamp_fields = {"first_seen", "last_seen", "due_at", "occurred_at", "completed_at"}
        if name in json_fields:
            return json.dumps(value), "jsonb", f"%({name})s::jsonb"
        if name in uuid_fields:
            return None if value is None else str(value), "uuid", f"%({name})s::uuid"
        if name in timestamp_fields:
            return value, "timestamptz", f"%({name})s::timestamptz"
        if name == "expected_closing_date":
            return value, "date", f"%({name})s::date"
        if name == "amount":
            return value, "numeric", f"%({name})s::numeric"
        if isinstance(value, bool):
            return value, "boolean", f"%({name})s"
        if isinstance(value, int):
            return value, "bigint", f"%({name})s"
        return value, "string", f"%({name})s"
