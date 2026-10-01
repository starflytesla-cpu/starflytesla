"""kie.ai 渠道加入 Gemini 3.8 Flash 看圖模型

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01

只執行一次的資料遷移：已經建立的 kie 渠道（建立時預設沒有模型）補上 gemini-3-8-flash-openai，
用途為看圖；該租戶還沒有預設看圖模型時設為預設。之後使用者刪除或修改都不會再被加回來。
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

MODEL_KEY = "gemini-3-8-flash-openai"


def upgrade() -> None:
    conn = op.get_bind()
    channels = conn.execute(
        sa.text("SELECT id, tenant_id FROM model_channels WHERE provider = 'kie' ORDER BY created_at")
    ).all()
    for channel_id, tenant_id in channels:
        exists = conn.execute(
            sa.text("SELECT 1 FROM channel_models WHERE channel_id = :c AND model_key = :k"),
            {"c": channel_id, "k": MODEL_KEY},
        ).first()
        if exists:
            continue
        has_default = conn.execute(
            sa.text(
                "SELECT 1 FROM channel_models cm JOIN model_channels mc ON mc.id = cm.channel_id "
                "WHERE mc.tenant_id = :t AND cm.capability = 'vision' AND cm.is_default"
            ),
            {"t": tenant_id},
        ).first()
        conn.execute(
            sa.text(
                "INSERT INTO channel_models (id, channel_id, model_key, display_name, capability, "
                "is_default, enabled, created_at) "
                "VALUES (:id, :c, :k, 'Gemini 3.8 Flash', 'vision', :d, true, :now)"
            ),
            {"id": str(uuid.uuid4()), "c": channel_id, "k": MODEL_KEY, "d": not has_default, "now": datetime.now(UTC)},
        )


def downgrade() -> None:
    # 資料遷移不回復：避免刪掉使用者之後自己調整過的模型設定
    pass
