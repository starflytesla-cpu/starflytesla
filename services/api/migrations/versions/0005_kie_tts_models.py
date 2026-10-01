"""kie.ai 渠道加入 ElevenLabs 配音模型

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01

只執行一次的資料遷移：既有的 kie 渠道補上 ElevenLabs Multilingual v2（租戶沒有預設配音模型時設為預設）
與 Turbo 2.5。之後使用者刪除或修改都不會再被加回來。
"""

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

MODELS = [
    ("elevenlabs/text-to-speech-multilingual-v2", "ElevenLabs Multilingual v2", True),
    ("elevenlabs/text-to-speech-turbo-2-5", "ElevenLabs Turbo 2.5（較便宜）", False),
]


def upgrade() -> None:
    conn = op.get_bind()
    channels = conn.execute(
        sa.text("SELECT id, tenant_id FROM model_channels WHERE provider = 'kie' ORDER BY created_at")
    ).all()
    now = datetime.now(UTC)
    for channel_id, tenant_id in channels:
        for offset, (key, name, want_default) in enumerate(MODELS):
            exists = conn.execute(
                sa.text("SELECT 1 FROM channel_models WHERE channel_id = :c AND model_key = :k"),
                {"c": channel_id, "k": key},
            ).first()
            if exists:
                continue
            has_default = conn.execute(
                sa.text(
                    "SELECT 1 FROM channel_models cm JOIN model_channels mc ON mc.id = cm.channel_id "
                    "WHERE mc.tenant_id = :t AND cm.capability = 'tts' AND cm.is_default"
                ),
                {"t": tenant_id},
            ).first()
            conn.execute(
                sa.text(
                    "INSERT INTO channel_models (id, channel_id, model_key, display_name, capability, "
                    "is_default, enabled, created_at) "
                    "VALUES (:id, :c, :k, :n, 'tts', :d, true, :now)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "c": channel_id,
                    "k": key,
                    "n": name,
                    "d": want_default and not has_default,
                    "now": now + timedelta(milliseconds=offset),
                },
            )


def downgrade() -> None:
    # 資料遷移不回復：避免刪掉使用者之後自己調整過的模型設定
    pass
