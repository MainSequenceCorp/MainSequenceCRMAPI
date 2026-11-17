"""Approved public owner read ports. No imported foreign table contracts or owner writes."""

import os
from decimal import Decimal, localcontext
from functools import wraps
from importlib import import_module

from .errors import ReportingError

KINDS = {
    "commercial": ["sales", "finance"],
    "operations": ["projects", "inventory", "purchasing", "manufacturing"],
}
RESOURCES = {
    "sales": "orders",
    "finance": "invoices",
    "projects": "projects",
    "inventory": "movements",
    "purchasing": "orders",
    "manufacturing": "orders",
}
SINGLE = {"sales", "purchasing"}
LABELS = {
    "sales": "Sales",
    "finance": "Finance",
    "projects": "Projects and services",
    "inventory": "Inventory",
    "purchasing": "Purchasing",
    "manufacturing": "Manufacturing",
}


def translate(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if all(hasattr(e, k) for k in ("status", "code", "message")):
                raise ReportingError(e.status, e.code, e.message) from e
            raise

    return call


class ReadPort:
    def __init__(self, owner, service):
        self.owner, self._service = owner, service

    @property
    def data_source_uid(self):
        return self._service.store.data_source_uid

    @translate
    def require(self):
        self._service.require(self.owner + ".read")

    @translate
    def collection(self, **query):
        args = [] if self.owner in SINGLE else [RESOURCES[self.owner]]
        return self._service.collection(*args, **query)

    @translate
    def get(self, uid):
        args = [] if self.owner in SINGLE else [RESOURCES[self.owner]]
        return self._service.get(*args, uid)


class Sources:
    def __init__(self, factories):
        self.factories = factories

    def port(self, name, source_uid):
        if name not in self.factories:
            raise ReportingError(
                503,
                "source_disabled",
                f"{LABELS[name]} is disabled; enable it before retrying this source step",
            )
        port = self.factories[name]()
        port.require()
        if str(port.data_source_uid) != str(source_uid):
            raise ReportingError(
                503,
                "source_mismatch",
                "Report source is outside the configured governed data source",
            )
        return port

    def authorize(self, names, source_uid):
        for name in names:
            self.port(name, source_uid)

    def capture(self, name, search, source_uid):
        port = self.port(name, source_uid)
        state = "confirmed" if name == "sales" else "posted" if name == "finance" else None
        first = port.collection(page_index=0, page_size=100, search=search, state=state)
        total = first["pageInfo"]["totalItems"]
        if total > 200:
            raise ReportingError(
                422,
                "source_limit",
                "More than 200 matching source records; narrow the saved report search and create a new run",
            )
        rows = list(first["items"])
        if total > 100:
            second = port.collection(page_index=1, page_size=100, search=search, state=state)
            if second["pageInfo"]["totalItems"] != total:
                raise ReportingError(
                    409,
                    "source_changed",
                    "Source collection changed during capture; retry this step",
                )
            rows += second["items"]
        if len(rows) != total or len({r["uid"] for r in rows}) != total:
            raise ReportingError(
                409, "source_changed", "Source collection changed during capture; retry this step"
            )
        return [project(name, r) for r in rows if name != "finance" or r["kind"] == "customer"]


def configured_sources(*, local=False):
    def factory(name):
        # These owner collection/get contracts require only their own read service.
        # No write dependencies are composed, and only read capabilities are passed.
        identity = import_module(f"api.erp.{name}.identity").actor_and_capabilities
        Service = import_module(f"src.erp.{name}.service").Service
        Store = import_module(f"src.erp.{name}.store").Store
        actor, caps = identity(local=local)
        return ReadPort(
            name, Service(Store(local_only=local), actor, set(caps) & {name + ".read"}, None)
        )

    return Sources(
        {
            name: lambda name=name: factory(name)
            for name in RESOURCES
            if os.environ.get("REPORTING_" + name.upper() + "_ENABLED", "true") != "false"
        }
    )


def project(owner, row):
    snapshot = row.get("snapshot") or {}
    result = {
        "uid": owner + "-" + str(row["uid"]),
        "source": owner,
        "source_uid": str(row["uid"]),
        "name": row["name"],
        "state": row["state"],
        "version": row["version"],
        "path": f"/{owner}/{RESOURCES[owner]}/{row['uid']}",
        "company_uid": str(
            row.get("operating_company_uid") or snapshot.get("operating_company_uid") or ""
        ),
        "company_name": row.get("company_name") or snapshot.get("company_name") or "",
        "currency_uid": str(row.get("currency_uid") or snapshot.get("currency_uid") or ""),
        "currency_code": row.get("currency_code") or snapshot.get("currency_code") or "",
        "net_total": str(row.get("net_total", "")),
        "total": str(row.get("total", "")),
        "allocated": str(row.get("allocated", "")),
        "remaining": "",
        "source_order_uid": str(row.get("source_order_uid") or ""),
    }
    if owner == "finance":
        with localcontext() as ctx:
            ctx.prec = 100
            result["remaining"] = str(Decimal(row["total"]) - Decimal(row["allocated"]))
    return result


def summarize(kind, rows):
    counts = {}
    for row in rows:
        k = (row["source"], row["state"])
        counts[k] = counts.get(k, 0) + 1
    result = {
        "record_count": len(rows),
        "counts": [
            {"source": s, "state": state, "count": count}
            for (s, state), count in sorted(counts.items())
        ],
    }
    if kind == "commercial":
        totals = {}
        orders = {r["source_uid"]: r for r in rows if r["source"] == "sales"}
        links = []
        with localcontext() as ctx:
            ctx.prec = 100
            for row in rows:
                k = (row["company_uid"], row["currency_uid"])
                group = totals.setdefault(
                    k,
                    {
                        "company_uid": k[0],
                        "currency_uid": k[1],
                        "company_name": row["company_name"],
                        "currency_code": row["currency_code"],
                        **{
                            x: Decimal(0)
                            for x in [
                                "order_net",
                                "invoice_net",
                                "invoice_total",
                                "allocated",
                                "remaining",
                            ]
                        },
                    },
                )
                if row["source"] == "sales":
                    group["order_net"] += Decimal(row["net_total"])
                else:
                    for target, source in [
                        ("invoice_net", "net_total"),
                        ("invoice_total", "total"),
                        ("allocated", "allocated"),
                        ("remaining", "remaining"),
                    ]:
                        group[target] += Decimal(row[source])
                    linked = orders.get(row["source_order_uid"])
                    status = (
                        "unlinked"
                        if not row["source_order_uid"]
                        else "outside_capture"
                        if linked is None
                        else "mismatch"
                        if (linked["company_uid"], linked["currency_uid"]) != k
                        else "matched"
                    )
                    links.append(
                        {
                            "invoice_uid": row["source_uid"],
                            "invoice_name": row["name"],
                            "order_uid": row["source_order_uid"],
                            "status": status,
                        }
                    )
        result["totals"] = [
            {k: str(v) if isinstance(v, Decimal) else v for k, v in g.items()}
            for _, g in sorted(totals.items())
        ]
        result["links"] = links
    return result
