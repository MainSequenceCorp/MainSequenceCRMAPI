"""Add durable identities for live banking and preserve existing file provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TABLE = "erp_finance__bank_movement_source"


def upgrade():
    op.add_column(TABLE, sa.Column("identity_kind", sa.String(24)))
    op.add_column(TABLE, sa.Column("identity_key", sa.String(100)))
    sources = sa.table(
        TABLE,
        sa.column("statement_sha256", sa.String(64)),
        sa.column("row_locator", sa.Integer()),
        sa.column("identity_kind", sa.String(24)),
        sa.column("identity_key", sa.String(100)),
    )
    op.execute(
        sources.update().values(
            identity_kind="statement_row",
            identity_key=sources.c.statement_sha256
            + ":"
            + sa.cast(sources.c.row_locator, sa.String()),
        ),
    )
    with op.batch_alter_table(TABLE) as batch:
        batch.alter_column("identity_kind", existing_type=sa.String(24), nullable=False)
        batch.alter_column("identity_key", existing_type=sa.String(100), nullable=False)
        batch.alter_column("statement_uid", existing_type=sa.Uuid(), nullable=True)
        batch.alter_column("statement_sha256", existing_type=sa.String(64), nullable=True)
        batch.alter_column("row_locator", existing_type=sa.Integer(), nullable=True)
        batch.create_unique_constraint(
            "uq_finance_bank_movement_identity",
            [
                "environment_uid",
                "installation_uid",
                "source_account_uid",
                "identity_kind",
                "identity_key",
            ],
        )


def downgrade():
    raise RuntimeError("Bank provenance requires a forward migration")
