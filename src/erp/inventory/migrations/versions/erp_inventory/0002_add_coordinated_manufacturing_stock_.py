"""Add coordinated manufacturing stock batches

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17 19:52:13.674573

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema; explicitly evolve usage checks that autogenerate does not detect."""
    with op.batch_alter_table('erp_inventory__location', schema=None) as batch_op:
        batch_op.drop_constraint('ck_inventory_location_usage', type_='check')
        batch_op.create_check_constraint('ck_inventory_location_usage', "usage IN ('internal','supplier','customer','adjustment','production')")
    with op.batch_alter_table('erp_inventory__move', schema=None) as batch_op:
        batch_op.add_column(sa.Column('manufacturing_order_uid', sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f('ix_erp_inventory__move_manufacturing_order_uid'), ['manufacturing_order_uid'], unique=False)
        batch_op.create_unique_constraint('uq_inventory_production_product', ['manufacturing_order_uid', 'stock_item_uid'])

    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema; caller must resolve production data before an explicit rollback."""
    with op.batch_alter_table('erp_inventory__location', schema=None) as batch_op:
        batch_op.drop_constraint('ck_inventory_location_usage', type_='check')
        batch_op.create_check_constraint('ck_inventory_location_usage', "usage IN ('internal','supplier','customer','adjustment')")
    with op.batch_alter_table('erp_inventory__move', schema=None) as batch_op:
        batch_op.drop_constraint('uq_inventory_production_product', type_='unique')
        batch_op.drop_index(batch_op.f('ix_erp_inventory__move_manufacturing_order_uid'))
        batch_op.drop_column('manufacturing_order_uid')

    # ### end Alembic commands ###
