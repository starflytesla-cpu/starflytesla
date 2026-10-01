"""kie.ai 渠道加入 Gemini 3.8 Flash TTS 並設為預設配音模型

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01

使用者 2026-10-01 指定改用 Gemini 3.8 Flash TTS（ElevenLabs 經 kie 出現 Internal Error）。
只執行一次的資料遷移：既有 kie 渠道補上 Gemini 3.8 Flash TTS 與 Lite，並把 Gemini 3.8 Flash TTS 設為該租戶的預設配音模型。
"""

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

MODELS = [
    ("google/gemini-3-8-flash-tts", "Gemini 3.8 Flash TTS"),
    ("google/gemini-3-8-flash-lite-tts", "Gemini 3.8 Flash Lite TTS（較便宜）"),
]


def upgrade() -> None:
    conn = op.get_bind()
    channels = conn.execute(
        sa.text("SELECT id, tenant_id FROM model_channels WHERE provider = 'kie' ORDER BY created_at")
    ).all()
    now = datetime.now(UTC)
    done_tenants: set[str] = set()
    for channel_id, tenant_id in channels:
        for offset, (key, name) in enumerate(MODELS):
            exists = conn.execute(
                sa.text("SELECT 1 FROM channel_models WHERE channel_id = :c AND model_key = :k"),
                {"c": channel_id, "k": key},
            ).first()
            if not exists:
                conn.execute(
                    sa.text(
                        "INSERT INTO channel_models (id, channel_id, model_key, display_name, capability, "
                        "is_default, enabled, created_at) VALUES (:id, :c, :k, :n, 'tts', false, true, :now)"
                    ),
                    {"id": str(uuid.uuid4()), "c": channel_id, "k": key, "n": name, "now": now + timedelta(milliseconds=offset)},
                )
        if tenant_id in done_tenants:
            continue
        done_tenants.add(tenant_id)
        # 每個租戶只把第一個 kie 渠道的 Gemini 3.8 Flash TTS 設為預設，其他配音模型取消預設
        conn.execute(
            sa.text(
                "UPDATE channel_models SET is_default = false WHERE capability = 'tts' AND channel_id IN "
                "(SELECT id FROM model_channels WHERE tenant_id = :t)"
            ),
            {"t": tenant_id},
        )
        conn.execute(
            sa.text(
                "UPDATE channel_models SET is_default = true, enabled = true "
                "WHERE channel_id = :c AND model_key = 'google/gemini-3-8-flash-tts'"
            ),
            {"c": channel_id},
        )


def downgrade() -> None:
    # 資料遷移不回復：避免刪掉使用者之後自己調整過的模型設定
    pass
