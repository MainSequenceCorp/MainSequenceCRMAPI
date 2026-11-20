"""CRM-owned portable statements through the governed MetaTables API."""

from functools import lru_cache
from threading import Lock

from metatables import MetaTable, MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import compile_sqlalchemy_statement, compile_sqlalchemy_statements
from src.erp.base.store import Store as BaseStore
from src.erp.crm.repositories.errors import ResourceConflict
from src.erp.module_access import execute_write, guard_write


class Store:
    def __init__(self, registry, *, require_active=False):
        self.require_active, self._active_checked = require_active, False
        self.registry = registry
        self.base = BaseStore()
        self._activation_lock = Lock()

    @property
    def data_source_uid(self):
        uid = self.registry.data_source_uid
        if str(uid) != self.base.data_source_uid:
            raise RuntimeError("CRM and Base must use the same governed DataSource")
        if self.require_active and not self._active_checked:
            with self._activation_lock:
                if not self._active_checked:
                    self.validate_activation(uid)
                    self._active_checked = True
        return uid

    def validate_activation(self, uid):
        from sqlalchemy import and_, func, or_, select

        from src.erp.base.metatables import Affiliation, Party

        from .reads import table

        links = table("base_identity_link")
        for resource, logical, model, kind in [
            ("companies", "company", Party, "organization"),
            ("contacts", "contact", Party, "person"),
            ("affiliations", "contact_company_affiliation", Affiliation, None),
        ]:
            source, target = table(logical), model.__table__
            joined = source.outerjoin(
                links, and_(links.c.resource == resource, links.c.record_uid == source.c.uid)
            ).outerjoin(target, target.c.uid == links.c.base_uid)
            bad = [
                links.c.uid.is_(None),
                links.c.state != "active",
                target.c.uid.is_(None),
                links.c.base_uid != source.c.uid,
            ]
            if kind:
                bad.append(target.c.kind != kind)
            query = select(func.count().label("count")).select_from(joined).where(or_(*bad))
            rows = MetaTable.execute_operation(
                compile_sqlalchemy_statement(
                    query,
                    operation="select",
                    data_source_uid=uid,
                    limits={"max_rows": 1, "statement_timeout_ms": 15000},
                )
            )["rows"]
            if int(rows[0]["count"]):
                raise RuntimeError(
                    "CRM Base adoption is incomplete; reconcile and activate extraction before starting this API"
                )

            after = None
            while True:
                query = (
                    select(source.c.uid, source.c.archived_at, target.c.consumers)
                    .select_from(joined)
                    .order_by(source.c.uid)
                    .limit(100)
                )
                if after:
                    from uuid import UUID

                    query = query.where(source.c.uid > UUID(after))
                batch = MetaTable.execute_operation(
                    compile_sqlalchemy_statement(
                        query,
                        operation="select",
                        data_source_uid=uid,
                        limits={"max_rows": 100, "statement_timeout_ms": 15000},
                    )
                )["rows"]
                if not batch:
                    break
                for row in batch:
                    claim = (row["consumers"] or {}).get("crm", {})
                    if (
                        claim.get("uid") != row["uid"]
                        or claim.get("logical") != logical
                        or claim.get("active") != (row["archived_at"] is None)
                    ):
                        raise RuntimeError("CRM Base consumer claims do not reconcile")
                after = batch[-1]["uid"]

    def read(self, statement, *, max_rows=100):
        return MetaTable.execute_operation(
            compile_sqlalchemy_statement(
                statement,
                operation="select",
                data_source_uid=self.data_source_uid,
                limits={"max_rows": max_rows, "statement_timeout_ms": 15000},
            )
        )["rows"]

    def write(self, statements):
        source = self.data_source_uid
        try:
            return execute_write(
                compile_sqlalchemy_statements(
                    guard_write("crm", source, statements),
                    operation="update",
                    data_source_uid=source,
                    limits={"max_rows": 100, "statement_timeout_ms": 15000},
                )
            )["rows"]
        except MetaTableTransactionGuardError as error:
            raise ResourceConflict(
                "Identity, profile or relationship changed; reload and review"
            ) from error


@lru_cache(maxsize=4)
def active_store(registry):
    """Share successful Base reconciliation for the process's catalog binding."""
    return Store(registry, require_active=True)
