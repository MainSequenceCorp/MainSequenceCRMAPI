"""Add integration selection to the shared versioned ERP policy."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "erp_user_preferences__environmentmoduleactivation",
        sa.Column("active_integration_keys", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.create_table(
        "erp_user_preferences__integrationactivationchange",
        sa.Column("uid", sa.Uuid(), primary_key=True),
        sa.Column("environment_uid", sa.Uuid(), nullable=False),
        sa.Column("request_uid", sa.Uuid(), nullable=False),
        sa.Column("actor_uid", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("integration_key", sa.String(128), nullable=False),
        sa.Column("previous_active", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint(
            "environment_uid", "request_uid", name="uq_erp_integration_activation_scope_request"
        ),
        sa.CheckConstraint("version > 0", name="ck_erp_integration_activation_change_version"),
    )


def downgrade():
    raise RuntimeError("ERP User Preferences preserves integration activation audit history")
