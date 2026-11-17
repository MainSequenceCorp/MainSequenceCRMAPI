"""Add reviewed category, purchase unit and reference-quantity contracts."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    for name in ("erp_catalog__unit", "erp_catalog__item"):
        if connection.execute(sa.text(f"SELECT count(*) FROM {name}")).scalar_one():
            raise RuntimeError(
                "Catalog draft units/items require a reviewed backfill before 0002; no reference basis or category is guessed"
            )
    op.create_table(
        "erp_catalog__category",
        sa.Column("uid", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.String(4000), nullable=False),
        sa.Column("parent_uid", sa.Uuid(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_uid", sa.Uuid(), nullable=False),
        sa.Column("updated_by_uid", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_uid"],
            ["erp_catalog__category.uid"],
            ondelete="RESTRICT",
            name="fk_catalog_category_parent",
        ),
        sa.CheckConstraint("version > 0", name="ck_erp_catalog__category_version"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_erp_catalog__category_name"),
    )
    op.create_index("ix_erp_catalog__category_parent_uid", "erp_catalog__category", ["parent_uid"])
    with op.batch_alter_table("erp_catalog__unit") as batch:
        batch.add_column(sa.Column("is_reference", sa.Boolean(), nullable=False))
        batch.add_column(sa.Column("rounding_increment", sa.String(40), nullable=False))
        batch.create_check_constraint(
            "ck_catalog_reference_factor", "NOT is_reference OR factor = '1'"
        )
    op.create_index(
        "uq_catalog_active_reference",
        "erp_catalog__unit",
        ["group_uid"],
        unique=True,
        sqlite_where=sa.text("is_reference = 1 AND archived_at IS NULL"),
        postgresql_where=sa.text("is_reference IS TRUE AND archived_at IS NULL"),
    )
    with op.batch_alter_table("erp_catalog__item") as batch:
        batch.add_column(sa.Column("category_uid", sa.Uuid(), nullable=False))
        batch.add_column(sa.Column("purchase_unit_uid", sa.Uuid(), nullable=False))
        batch.add_column(sa.Column("sale_description", sa.String(4000), nullable=False))
        batch.add_column(sa.Column("purchase_description", sa.String(4000), nullable=False))
        batch.create_foreign_key(
            "fk_catalog_item_category",
            "erp_catalog__category",
            ["category_uid"],
            ["uid"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_catalog_item_purchase_unit",
            "erp_catalog__unit",
            ["purchase_unit_uid"],
            ["uid"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_erp_catalog__item_category_uid", ["category_uid"])
        batch.create_index("ix_erp_catalog__item_purchase_unit_uid", ["purchase_unit_uid"])


def downgrade():
    raise RuntimeError(
        "Catalog 0002 has no automatic destructive downgrade; restore a reviewed backup or roll forward"
    )
