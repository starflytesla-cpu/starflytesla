"""模型渠道診斷：python -m app.diagnostics（維運指令 ops.sh ai-check 會呼叫）

列出每個渠道的設定概況；豆包方舟渠道再實測 Key 在 BytePlus 國際版與火山引擎中國區能否通過驗證。
倉庫是公開的、Actions 記錄任何人都看得到：這裡絕對不輸出 API Key 或其中任何片段。
"""

import uuid
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import get_sessionmaker
from app.models import ModelChannel
from app.security import decrypt_secret
from app.services import ai_provider


def _verdict(status: int | None, control: int | None) -> str:
    if status is None:
        return "連線失敗"
    if status == 401:
        return "401 不認得這把 Key"
    if status >= 500:
        return f"{status} 上游錯誤，無法判斷"
    if control != 401:
        return f"{status}（假 Key 也回 {control}，無法判斷）"
    return f"{status} 驗證通過（Key 屬於這裡）"


def main() -> None:
    with get_sessionmaker()() as db:
        channels = db.scalars(select(ModelChannel).options(selectinload(ModelChannel.models)).order_by(ModelChannel.created_at)).all()
        if not channels:
            print("（沒有任何渠道）")
        for channel in channels:
            api_key = decrypt_secret(channel.api_key_encrypted)
            print(f"== {channel.name}（{channel.provider}，{'啟用' if channel.enabled else '停用'}）")
            print(f"  Base URL 主機：{urlsplit(channel.base_url).hostname}")
            print(f"  API Key：{ai_provider.describe_key(api_key)}")
            models = ", ".join(f"{m.model_key}[{m.capability}{'/停用' if not m.enabled else ''}]" for m in channel.models)
            print(f"  模型：{models or '（無）'}")
            if not api_key or not ai_provider.is_ark(channel.provider, channel.base_url):
                continue
            print("  方舟 Key 驗證：")
            for label, url in ai_provider.ARK_ENDPOINTS.values():
                status = ai_provider.probe_ark_auth(url, api_key)
                control = ai_provider.probe_ark_auth(url, str(uuid.uuid4()))
                current = "（目前設定）" if channel.base_url.rstrip("/") == url else ""
                print(f"    {label}{current}：{_verdict(status, control)}")


if __name__ == "__main__":
    main()
