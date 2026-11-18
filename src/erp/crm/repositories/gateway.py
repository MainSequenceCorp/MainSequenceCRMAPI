"""Shared, provider-bound Main Sequence MetaTable operation gateway."""

from __future__ import annotations

import json
from typing import Any

from metatables import MetaTable
from metatables.compiled_sql.v1 import compile_sqlalchemy_statements
from metatables.models import MetaTableTransactionStatement
from src.erp.module_access import admitted_guards, execute_write

from ..platform.catalog import CatalogRegistry, configured_registry
from ..platform.diagnostics import observe_stage


class GovernedGateway:
    def __init__(self, registry: CatalogRegistry | None = None):
        self.registry = registry or configured_registry()

    def _operation(
        self,
        *,
        operation: str,
        sql: str,
        parameters: dict[str, Any],
        parameter_types: dict[str, str],
        max_rows: int = 1000,
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
                key: value for key, value in parameter_types.items() if value in {"json", "jsonb"}
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
