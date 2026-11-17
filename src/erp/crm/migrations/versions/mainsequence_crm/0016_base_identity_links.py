"""Track controlled Base adoption without changing historical CRM identities."""
import sqlalchemy as sa
from alembic import op
revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mainsequence_crm__base_identity_link',
        sa.Column('uid', sa.Uuid(), primary_key=True),
        sa.Column('resource', sa.String(40), nullable=False),
        sa.Column('record_uid', sa.Uuid(), nullable=False),
        sa.Column('base_uid', sa.Uuid(), nullable=False),
        sa.Column('source_version', sa.BigInteger(), nullable=False),
        sa.Column('source_digest', sa.String(64), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by_uid', sa.Uuid(), nullable=False),
        sa.UniqueConstraint('resource', 'record_uid', name='uq_crm_base_identity_record'))


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM mainsequence_crm__base_identity_link')).scalar():
        raise RuntimeError('Reconcile and detach Base adoption before downgrading CRM')
    op.drop_table('mainsequence_crm__base_identity_link')
