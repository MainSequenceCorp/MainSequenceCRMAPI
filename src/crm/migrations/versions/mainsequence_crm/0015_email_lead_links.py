"""Associate shared email conversations with reviewed Leads explicitly."""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None
TABLE = "mainsequence_crm__email_lead_link"


def upgrade():
    op.create_table(TABLE,
        sa.Column("uid", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_uid", sa.Uuid()), sa.Column("updated_by_uid", sa.Uuid()),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("interaction_uid", sa.Uuid(), sa.ForeignKey("mainsequence_crm__interaction.uid"), nullable=False),
        sa.Column("lead_uid", sa.Uuid(), sa.ForeignKey("mainsequence_crm__solution_selling_lead.uid"), nullable=False),
        sa.UniqueConstraint("interaction_uid", "lead_uid", name="uq_crm_email_lead_link"),
        sa.CheckConstraint("version > 0", name="ck_crm_email_lead_link_version"))
    op.create_index("ix_crm_email_lead_link_lead", TABLE, ["lead_uid", "interaction_uid"])


def downgrade():
    op.drop_table(TABLE)
