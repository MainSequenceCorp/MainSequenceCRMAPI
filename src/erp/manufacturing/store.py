"""Governed MetaTables storage. Application code never opens a database file."""

from functools import cached_property

from metatables import MetaTable, get_runtime_status
from metatables.compiled_sql.v1 import compile_sqlalchemy_statement, compile_sqlalchemy_statements
from src.erp.manufacturing.metatables import MODELS
from src.erp.module_access import execute_write, guard_write


def require_local_runtime():
    state = get_runtime_status()
    source = state.get("data_source") or {}
    bootstrap = state.get("bootstrap") or {}
    if not (
        state.get("local_mode") is True
        and state.get("dialect") == "sqlite"
        and source.get("class_type") == "sqlite"
        and source.get("uid")
        and bootstrap.get("active") is True
        and bootstrap.get("status") == "ready"
        and not state.get("data_source_error")
    ):
        raise RuntimeError(
            "Manufacturing local verification requires initialized MetaTables local SQLite"
        )
    return source["uid"]


class Store:
    def __init__(self, *, local_only=False):
        self.local_only = local_only

    @cached_property
    def data_source_uid(self):
        expected_source = require_local_runtime() if self.local_only else None
        expected = {model.__metatable_identifier__: model.__tablename__ for model in MODELS}
        rows = MetaTable.filter(identifier__in=list(expected), provisioning_status="active")
        if len(rows) != len(expected) or {row.identifier for row in rows} != set(expected):
            raise RuntimeError("Manufacturing migration bindings are incomplete")
        sources, providers, revisions = set(), set(), set()
        for row in rows:
            if (
                row.physical_table_name != expected[row.identifier]
                or row.physical_schema not in (None, "", "public")
                or row.management_mode != "platform_managed"
                or row.schema_management_mode != "alembic_managed"
                or row.migration_namespace != "erp-manufacturing"
                or not any(ns.name == "erp-manufacturing" for ns in row.namespaces)
            ):
                raise RuntimeError(
                    "Manufacturing table manufacturing ownership does not match its provider"
                )
            sources.add(str(row.data_source_uid))
            providers.add(row.migration_provider_key)
            revisions.add(row.alembic_revision)
        if (
            len(sources) != 1
            or providers != {"src.erp.manufacturing:erp-manufacturing"}
            or revisions != {"0001"}
            or None in providers
        ):
            raise RuntimeError(
                "Manufacturing table manufacturing contains inconsistent revisions or sources"
            )
        source = sources.pop()
        if expected_source and source != str(expected_source):
            raise RuntimeError("Manufacturing tables are outside the verified local DataSource")
        return source

    def read(self, statement, *, max_rows=100):
        result = MetaTable.execute_operation(
            compile_sqlalchemy_statement(
                statement,
                operation="select",
                data_source_uid=self.data_source_uid,
                limits={"max_rows": max_rows, "statement_timeout_ms": 10000},
            )
        )
        return result["rows"]

    def write(self, statements):
        if self.local_only and str(require_local_runtime()) != self.data_source_uid:
            raise RuntimeError("Local DataSource changed; restart Manufacturing before writing")
        result = execute_write(
            compile_sqlalchemy_statements(
                guard_write("manufacturing", self.data_source_uid, statements),
                operation="update",
                data_source_uid=self.data_source_uid,
                limits={"max_rows": 100, "statement_timeout_ms": 10000},
            )
        )
        return result["rows"]
