"""Shared governed page execution for module-owned collection queries."""

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Text, Uuid, cast, func, literal, select, true
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import ColumnElement, UnaryExpression
from sqlalchemy.sql.functions import FunctionElement

from src.erp.module_access.collections import collection_admission


def _split_ordering(ordering):
    modifiers = []
    while isinstance(ordering, UnaryExpression) and ordering.modifier in (
        operators.asc_op,
        operators.desc_op,
        operators.nulls_first_op,
        operators.nulls_last_op,
    ):
        modifiers.append(ordering.modifier)
        ordering = ordering.element
    return ordering, modifiers


def _order(columns, modifiers):
    for column, operations in zip(columns, modifiers, strict=True):
        for operation in reversed(operations):
            column = operation(column)
        yield column


def page_result(items, total, page_index, page_size):
    return {
        "items": items,
        "pageInfo": {
            "pageIndex": page_index,
            "pageSize": page_size,
            "totalItems": total,
            "hasNextPage": (page_index + 1) * page_size < total,
            "hasPreviousPage": page_index > 0,
        },
    }


class _JsonObject(FunctionElement):
    type = JSON()
    inherit_cache = True


class _JsonArray(FunctionElement):
    type = JSON()
    inherit_cache = True


@compiles(_JsonObject, "postgresql")
@compiles(_JsonObject, "sqlite")
def _compile_object(element, compiler, **kwargs):
    name = "json_object" if compiler.dialect.name == "sqlite" else "jsonb_build_object"
    return f"{name}({compiler.process(element.clauses, **kwargs)})"


@compiles(_JsonArray, "postgresql")
@compiles(_JsonArray, "sqlite")
def _compile_array(element, compiler, **kwargs):
    name = "json_group_array" if compiler.dialect.name == "sqlite" else "jsonb_agg"
    return f"{name}({compiler.process(element.clauses, **kwargs)})"


def json_rows(statement):
    """Project a bounded, ordered child selection as a scalar array."""
    child = statement.subquery()
    members = [
        argument
        for column in child.c
        for argument in (cast(literal(str(column.name)), Text), column)
    ]
    return select(_JsonArray(_JsonObject(*members))).select_from(child).scalar_subquery()


def decode_json_rows(value, table):
    if value is None:
        return []
    rows = json.loads(value) if isinstance(value, str) else value
    uuid_fields = [column.name for column in table.c if isinstance(column.type, Uuid)]
    timestamp_fields = [column.name for column in table.c if isinstance(column.type, DateTime)]
    for row in rows:
        for field in uuid_fields:
            if row.get(field) is not None:
                row[field] = str(UUID(str(row[field])))
        for field in timestamp_fields:
            if row.get(field) is not None:
                timestamp = datetime.fromisoformat(row[field])
                row[field] = (
                    timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
                ).isoformat()
    return rows


def read_page(
    store,
    table,
    predicates: Sequence,
    ordering: Sequence,
    *,
    page_index: int,
    page_size: int,
    projection: Sequence | None = None,
    from_clause=None,
    match_from=None,
    parent: tuple[ColumnElement, Exception] | None = None,
) -> dict[str, Any]:
    """Read an exact count and bounded page in one statement.

    Predicates and ordering are supplied by the module, using bound values.
    A projection may join data after the page has been selected. It must
    preserve its identity column and yield at most one row per selected ID.
    """
    keys = [_split_ordering(value) for value in ordering]
    sort_names = [f"_erp_sort_{index}" for index in range(len(keys))]
    ordering_modifiers = [modifiers for _, modifiers in keys]
    matching = (
        select(
            table.c.uid,
            *(
                expression.label(name)
                for (expression, _), name in zip(keys, sort_names, strict=True)
            ),
        )
        .select_from(table if match_from is None else match_from)
        .where(*predicates)
    )
    if parent is not None:
        visible = select(parent[0].label("_erp_parent_visible")).cte("erp_visible_parent")
        matching = matching.where(select(visible.c._erp_parent_visible).scalar_subquery())
    pending = collection_admission.get()
    if pending is not None:
        decision = pending.decision(store.data_source_uid)
        matching = matching.where(
            select(decision.c._erp_policy_state).scalar_subquery() == "allowed"
        )
    matching = matching.cte("erp_matching")
    sort_keys = [matching.c[name] for name in sort_names]
    page = (
        select(matching)
        .order_by(*_order(sort_keys, ordering_modifiers))
        .limit(page_size)
        .offset(page_index * page_size)
        .cte("erp_page")
    )
    total = select(func.count().label("_erp_total")).select_from(matching).cte("erp_total")
    columns = list(table.c) if projection is None else projection
    projected = (
        select(*columns, *(page.c[name] for name in sort_names))
        .select_from(
            page.join(table if from_clause is None else from_clause, table.c.uid == page.c.uid)
        )
        .cte("erp_projected")
    )
    source = total if parent is None else total.join(visible, true())
    if pending is not None:
        source = source.join(decision, true())
    statement = select(total.c._erp_total, projected).select_from(
        source.outerjoin(projected, true())
    )
    if parent is not None:
        statement = statement.add_columns(visible.c._erp_parent_visible)
    if pending is not None:
        statement = statement.add_columns(decision.c._erp_policy_state)
    statement = statement.order_by(
        *_order([projected.c[name] for name in sort_names], ordering_modifiers)
    )
    started = perf_counter()
    rows = store.read(statement, max_rows=page_size)
    if not rows:
        raise RuntimeError("ERP collection returned no result envelope")
    if pending is not None:
        pending.data_ms = (perf_counter() - started) * 1000
        pending.verify(rows[0]["_erp_policy_state"])
    if parent is not None and not rows[0]["_erp_parent_visible"]:
        raise parent[1]
    internal = {"_erp_total", "_erp_parent_visible", "_erp_policy_state", *sort_names}
    items = [
        {key: value for key, value in row.items() if key not in internal}
        for row in rows
        if row["uid"] is not None
    ]
    return page_result(items, int(rows[0]["_erp_total"]), page_index, page_size)
