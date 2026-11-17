"""Add lossless identity, precise relationship periods and consumer claims."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("erp_base__party", "erp_base__affiliation"):
        for name in ("consumers", "provenance"):
            op.add_column(table, sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("erp_base__party", sa.Column("identity", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    # SQLite stores unbounded text regardless of a VARCHAR display length.
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("erp_base__party", "name", existing_type=sa.String(200), type_=sa.String(511), existing_nullable=False)
    op.add_column("erp_base__affiliation", sa.Column("status", sa.String(10), nullable=False, server_default="unknown"))
    for name in ("started_period", "ended_period"):
        op.add_column("erp_base__affiliation", sa.Column(name, sa.String(10)))
    op.add_column("erp_base__affiliation", sa.Column("job_title", sa.String(255)))


def downgrade():
    # Extracted information cannot be discarded by an automatic downgrade.
    for table in ("erp_base__party", "erp_base__affiliation"):
        rows = op.get_bind().execute(sa.text(f"SELECT consumers FROM {table}"))
        if any(value not in ({}, "{}", None) for (value,) in rows):
            raise RuntimeError("Detach and reconcile adopted records before downgrading Base")
    for name in ("status", "started_period", "ended_period", "job_title"):
        op.drop_column("erp_base__affiliation", name)
    op.drop_column("erp_base__party", "identity")
    for table in ("erp_base__party", "erp_base__affiliation"):
        for name in ("consumers", "provenance"):
            op.drop_column(table, name)
