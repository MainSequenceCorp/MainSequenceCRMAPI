"""Add provider-independent Finance banking reconciliation storage."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "erp_finance__bank_account",
        sa.Column("environment_uid", sa.Uuid(), nullable=False),
        sa.Column("company_uid", sa.Uuid(), nullable=False),
        sa.Column("currency_uid", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("masked_label", sa.String(length=128), nullable=False),
        sa.Column("intake_version", sa.BigInteger(), nullable=False),
        sa.Column("uid", sa.Uuid(), primary_key=True),
        sa.UniqueConstraint("environment_uid", "company_uid", "fingerprint", "currency_uid"),
    )
    op.create_table(
        "erp_finance__bank_source_account_map",
        sa.Column("environment_uid", sa.Uuid(), nullable=False),
        sa.Column("installation_uid", sa.Uuid(), nullable=False),
        sa.Column("source_account_uid", sa.Uuid(), nullable=False),
        sa.Column(
            "bank_account_uid",
            sa.Uuid(),
            sa.ForeignKey("erp_finance__bank_account.uid"),
            nullable=False,
        ),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("actor_uid", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uid", sa.Uuid(), primary_key=True),
        sa.UniqueConstraint("environment_uid", "installation_uid", "source_account_uid"),
    )
    op.create_index(
        "ix_erp_finance__bank_source_account_map_bank_account_uid",
        "erp_finance__bank_source_account_map",
        ["bank_account_uid"],
    )
    op.create_table(
        "erp_finance__bank_counterparty_alias",
        sa.Column("environment_uid", sa.Uuid(), nullable=False),
        sa.Column("company_uid", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("party_uid", sa.Uuid(), nullable=False),
        sa.Column("actor_uid", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uid", sa.Uuid(), primary_key=True),
        sa.UniqueConstraint("environment_uid", "company_uid", "fingerprint"),
    )
    op.create_table(
        "erp_finance__bank_movement",
        sa.Column(
            "bank_account_uid",
            sa.Uuid(),
            sa.ForeignKey("erp_finance__bank_account.uid"),
            nullable=False,
        ),
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("signed_amount", sa.String(length=40), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("party_uid", sa.Uuid(), nullable=True),
        sa.Column(
            "payment_uid", sa.Uuid(), sa.ForeignKey("erp_finance__payment.uid"), nullable=True
        ),
        sa.Column(
            "reverses_movement_uid",
            sa.Uuid(),
            sa.ForeignKey("erp_finance__bank_movement.uid"),
            nullable=True,
        ),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("actor_uid", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uid", sa.Uuid(), primary_key=True),
        sa.UniqueConstraint("payment_uid"),
    )
    op.create_index(
        "ix_erp_finance__bank_movement_bank_account_uid",
        "erp_finance__bank_movement",
        ["bank_account_uid"],
    )
    op.create_table(
        "erp_finance__bank_movement_source",
        sa.Column(
            "movement_uid",
            sa.Uuid(),
            sa.ForeignKey("erp_finance__bank_movement.uid"),
            nullable=False,
        ),
        sa.Column("environment_uid", sa.Uuid(), nullable=False),
        sa.Column("installation_uid", sa.Uuid(), nullable=False),
        sa.Column("source_account_uid", sa.Uuid(), nullable=False),
        sa.Column("adapter_key", sa.String(length=64), nullable=False),
        sa.Column("statement_uid", sa.Uuid(), nullable=False),
        sa.Column("statement_sha256", sa.String(length=64), nullable=False),
        sa.Column("row_locator", sa.Integer(), nullable=False),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("uid", sa.Uuid(), primary_key=True),
        sa.UniqueConstraint(
            "environment_uid",
            "installation_uid",
            "source_account_uid",
            "statement_sha256",
            "row_locator",
        ),
    )
    op.create_index(
        "ix_erp_finance__bank_movement_source_movement_uid",
        "erp_finance__bank_movement_source",
        ["movement_uid"],
    )
    op.create_table(
        "erp_finance__bank_review",
        sa.Column("environment_uid", sa.Uuid(), nullable=False),
        sa.Column("actor_uid", sa.Uuid(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uid", sa.Uuid(), primary_key=True),
    )
    op.create_index(
        "ix_erp_finance__bank_review_environment_uid",
        "erp_finance__bank_review",
        ["environment_uid"],
    )
    op.create_table(
        "erp_finance__bank_intake_operation",
        sa.Column("environment_uid", sa.Uuid(), nullable=False),
        sa.Column("actor_uid", sa.Uuid(), nullable=False),
        sa.Column("request_uid", sa.Uuid(), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uid", sa.Uuid(), primary_key=True),
        sa.UniqueConstraint("environment_uid", "actor_uid", "request_uid"),
    )
    op.create_table(
        "erp_finance__bank_grant_fence",
        sa.Column("environment_uid", sa.Uuid(), nullable=False),
        sa.Column("installation_uid", sa.Uuid(), nullable=False),
        sa.Column("binding_key", sa.String(length=128), nullable=False),
        sa.Column("binding_generation", sa.BigInteger(), nullable=False),
        sa.Column("connection_uid", sa.Uuid(), nullable=False),
        sa.Column("source_account_uid", sa.Uuid(), nullable=False),
        sa.Column("actor_uid", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(length=8), nullable=False),
        sa.Column("uid", sa.Uuid(), primary_key=True),
    )
    op.create_index(
        "ix_erp_finance__bank_grant_fence_environment_uid",
        "erp_finance__bank_grant_fence",
        ["environment_uid"],
    )


def downgrade():
    raise RuntimeError("Finance banking history requires a forward migration")
