"""發佈渠道與成本帳本的渠道關聯

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-05 09:03:04.897652
"""

from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('publish_channels',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('base_url', sa.String(length=500), nullable=False),
    sa.Column('api_key_encrypted', sa.Text(), nullable=False),
    sa.Column('api_key_last4', sa.String(length=8), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('check_status', sa.String(length=16), nullable=False),
    sa.Column('check_error', sa.String(length=500), nullable=False),
    sa.Column('plan', sa.String(length=80), nullable=False),
    sa.Column('checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_publish_channels_tenant_id'), 'publish_channels', ['tenant_id'], unique=False)
    op.add_column('usage_ledger', sa.Column('publish_channel_id', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_usage_ledger_publish_channel_id'), 'usage_ledger', ['publish_channel_id'], unique=False)
    op.create_foreign_key('fk_usage_ledger_publish_channel_id', 'usage_ledger', 'publish_channels', ['publish_channel_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_usage_ledger_publish_channel_id', 'usage_ledger', type_='foreignkey')
    op.drop_index(op.f('ix_usage_ledger_publish_channel_id'), table_name='usage_ledger')
    op.drop_column('usage_ledger', 'publish_channel_id')
    op.drop_index(op.f('ix_publish_channels_tenant_id'), table_name='publish_channels')
    op.drop_table('publish_channels')
