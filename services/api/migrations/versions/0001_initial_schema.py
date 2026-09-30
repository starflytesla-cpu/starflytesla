"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-09-30 15:29:13.892257
"""

from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('tenants',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('model_channels',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('base_url', sa.String(length=500), nullable=False),
    sa.Column('api_key_encrypted', sa.Text(), nullable=False),
    sa.Column('api_key_last4', sa.String(length=8), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_model_channels_tenant_id'), 'model_channels', ['tenant_id'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('display_name', sa.String(length=80), nullable=False),
    sa.Column('password_hash', sa.String(length=128), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('token_version', sa.Integer(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'], unique=False)
    op.create_table('channel_models',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('channel_id', sa.String(length=36), nullable=False),
    sa.Column('model_key', sa.String(length=160), nullable=False),
    sa.Column('display_name', sa.String(length=160), nullable=False),
    sa.Column('capability', sa.String(length=16), nullable=False),
    sa.Column('input_price_per_m', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('output_price_per_m', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['channel_id'], ['model_channels.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('channel_id', 'model_key')
    )
    op.create_index(op.f('ix_channel_models_capability'), 'channel_models', ['capability'], unique=False)
    op.create_index(op.f('ix_channel_models_channel_id'), 'channel_models', ['channel_id'], unique=False)
    op.create_table('usage_ledger',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('action', sa.String(length=48), nullable=False),
    sa.Column('source', sa.String(length=48), nullable=False),
    sa.Column('channel_id', sa.String(length=36), nullable=True),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('model_key', sa.String(length=160), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('input_tokens', sa.BigInteger(), nullable=False),
    sa.Column('output_tokens', sa.BigInteger(), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('cost_micros', sa.BigInteger(), nullable=True),
    sa.Column('currency', sa.String(length=8), nullable=False),
    sa.Column('error', sa.String(length=500), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['channel_id'], ['model_channels.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_usage_ledger_action'), 'usage_ledger', ['action'], unique=False)
    op.create_index(op.f('ix_usage_ledger_channel_id'), 'usage_ledger', ['channel_id'], unique=False)
    op.create_index(op.f('ix_usage_ledger_created_at'), 'usage_ledger', ['created_at'], unique=False)
    op.create_index(op.f('ix_usage_ledger_status'), 'usage_ledger', ['status'], unique=False)
    op.create_index(op.f('ix_usage_ledger_tenant_id'), 'usage_ledger', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_usage_ledger_user_id'), 'usage_ledger', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_usage_ledger_user_id'), table_name='usage_ledger')
    op.drop_index(op.f('ix_usage_ledger_tenant_id'), table_name='usage_ledger')
    op.drop_index(op.f('ix_usage_ledger_status'), table_name='usage_ledger')
    op.drop_index(op.f('ix_usage_ledger_created_at'), table_name='usage_ledger')
    op.drop_index(op.f('ix_usage_ledger_channel_id'), table_name='usage_ledger')
    op.drop_index(op.f('ix_usage_ledger_action'), table_name='usage_ledger')
    op.drop_table('usage_ledger')
    op.drop_index(op.f('ix_channel_models_channel_id'), table_name='channel_models')
    op.drop_index(op.f('ix_channel_models_capability'), table_name='channel_models')
    op.drop_table('channel_models')
    op.drop_index(op.f('ix_users_tenant_id'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_model_channels_tenant_id'), table_name='model_channels')
    op.drop_table('model_channels')
    op.drop_table('tenants')
