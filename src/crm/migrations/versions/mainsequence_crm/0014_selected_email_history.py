"""Add reviewed email history; existing Google grants do not enroll anything."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None
THREAD = "mainsequence_crm__email_thread"
MESSAGE = "mainsequence_crm__email_message"
TASK = "mainsequence_crm__task"


def versioned():
    return [sa.Column("uid", sa.Uuid(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by_uid", sa.Uuid()), sa.Column("updated_by_uid", sa.Uuid()),
            sa.Column("version", sa.BigInteger(), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True))]


def upgrade():
    op.create_table(THREAD, *versioned(),
        sa.Column("contact_uid", sa.Uuid(), sa.ForeignKey("mainsequence_crm__contact.uid"), nullable=False),
        sa.Column("interaction_uid", sa.Uuid(), sa.ForeignKey("mainsequence_crm__interaction.uid"), nullable=False),
        sa.Column("actor_uid", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("provider_thread_id", sa.String(256)),
        sa.Column("sync_enabled", sa.Boolean(), nullable=False),
        sa.Column("sync_after_ms", sa.BigInteger()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("source_key", "provider_thread_id", name="uq_crm_email_thread_source"),
        sa.CheckConstraint("version > 0", name="ck_crm_email_thread_version"),
        sa.CheckConstraint("NOT sync_enabled OR (provider_thread_id IS NOT NULL AND sync_after_ms IS NOT NULL)", name="ck_crm_email_thread_selection"))
    op.create_index("ix_crm_email_thread_sync", THREAD, ["actor_uid", "sync_enabled", "last_synced_at"])
    op.create_table(MESSAGE, *versioned(),
        sa.Column("thread_uid", sa.Uuid(), sa.ForeignKey(THREAD + ".uid"), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("provider_message_id", sa.String(256)),
        sa.Column("rfc_message_id", sa.String(1000)),
        sa.Column("sender", JSONB(), nullable=False),
        sa.Column("to", JSONB(), nullable=False), sa.Column("cc", JSONB(), nullable=False),
        sa.Column("subject", sa.String(2000), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("internal_date_ms", sa.BigInteger()),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_state", sa.String(20), nullable=False),
        sa.Column("original_url", sa.String(2048)),
        sa.UniqueConstraint("source_key", "provider_message_id", name="uq_crm_email_message_source"),
        sa.CheckConstraint("version > 0", name="ck_crm_email_message_version"),
        sa.CheckConstraint("source IN ('manual','gmail')", name="ck_crm_email_message_source"),
        sa.CheckConstraint("body_state IN ('complete','unavailable')", name="ck_crm_email_message_body"))
    op.create_index("ix_crm_email_message_thread", MESSAGE, ["thread_uid", "internal_date_ms", "uid"])
    op.create_index("ix_crm_email_message_date", MESSAGE, ["sent_at", "uid"])
    with op.batch_alter_table(TASK) as batch:
        batch.add_column(sa.Column("source_email_message_uid", sa.Uuid()))
        batch.create_foreign_key("fk_crm_task_email", MESSAGE, ["source_email_message_uid"], ["uid"])

    op.create_index("uq_crm_task_open_email", TASK, ["source_email_message_uid"], unique=True, postgresql_where=sa.text("source_email_message_uid IS NOT NULL AND completed_at IS NULL AND archived_at IS NULL"), sqlite_where=sa.text("source_email_message_uid IS NOT NULL AND completed_at IS NULL AND archived_at IS NULL"))


def downgrade():
    op.drop_index("uq_crm_task_open_email", table_name=TASK)
    with op.batch_alter_table(TASK) as batch:
        batch.drop_constraint("fk_crm_task_email", type_="foreignkey")
        batch.drop_column("source_email_message_uid")
    op.drop_table(MESSAGE)
    op.drop_table(THREAD)
