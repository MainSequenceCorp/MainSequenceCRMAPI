"""Create private ERP preferences, activation policy, change audit and transaction lock."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "erp_user_preferences__userpreference",
        sa.Column("uid", sa.Uuid(), primary_key=True),
        sa.Column("environment_uid", sa.Uuid(), nullable=False),
        sa.Column("person_uid", sa.Uuid(), nullable=False),
        sa.Column("hidden_module_keys", sa.JSON(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "environment_uid", "person_uid", name="uq_erp_preferences_scope_person"
        ),
        sa.CheckConstraint("version > 0", name="ck_erp_preferences_version"),
    )
    op.create_table(
        "erp_user_preferences__environmentmoduleactivation",
        sa.Column("environment_uid", sa.Uuid(), primary_key=True),
        sa.Column("active_module_keys", sa.JSON(), nullable=False),
        sa.Column("actor_uid", sa.Uuid(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_erp_activation_version"),
    )
    op.create_table(
        "erp_user_preferences__moduleactivationchange",
        sa.Column("uid", sa.Uuid(), primary_key=True),
        sa.Column("environment_uid", sa.Uuid(), nullable=False),
        sa.Column("request_uid", sa.Uuid(), nullable=False),
        sa.Column("actor_uid", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("previous_module_keys", sa.JSON(), nullable=False),
        sa.Column("active_module_keys", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "environment_uid", "request_uid", name="uq_erp_activation_scope_request"
        ),
        sa.CheckConstraint("version > 0", name="ck_erp_activation_change_version"),
    )
    op.create_table(
        "erp_user_preferences__moduleadmissionlock",
        sa.Column("environment_uid", sa.Uuid(), primary_key=True),
        sa.Column("lock_marker", sa.BigInteger(), nullable=False),
    )


def downgrade():
    raise RuntimeError("ERP User Preferences preserves settings and activation audit history")
