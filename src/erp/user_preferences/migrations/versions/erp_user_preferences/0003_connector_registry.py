"""Persist published ERP connector registries and the active revision pointer."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "erp_user_preferences__environmentmoduleactivation",
        sa.Column("connector_registry_revision", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.create_table(
        "erp_user_preferences__connectorregistryrevision",
        sa.Column("environment_uid", sa.Uuid(), primary_key=True),
        sa.Column("revision", sa.BigInteger(), primary_key=True),
        sa.Column("published_by_uid", sa.Uuid(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_yaml", sa.Text(), nullable=False),
        sa.Column("bindings", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_erp_registry_revision"),
    )


def downgrade():
    raise RuntimeError("ERP preserves immutable connector registry publication history")
