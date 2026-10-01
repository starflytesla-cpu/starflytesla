"""模型渠道預設。價格為每百萬 token 的美元價格，僅供成本估算，可在後台修改。

價格來源（2026-09 查詢）：
- DeepSeek：https://api-docs.deepseek.com/quick_start/pricing（採尖峰價，離峰為一半）
- BytePlus ModelArk：價格依模型與區域而異，請到 BytePlus 控制台確認後在後台填入
- kie.ai：以點數計費（https://kie.ai/pricing），換算成每百萬 token 價格後在後台填入
"""

from decimal import Decimal

CAPABILITIES = {
    "text": "文字（文案、翻譯、評論）",
    "vision": "看圖（素材打標籤）",
    "tts": "配音",
    "embedding": "向量（素材檢索）",
}

PRESETS: dict[str, dict] = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "api_key_help": "在 https://platform.deepseek.com/api_keys 建立",
        "models": [
            {
                "model_key": "deepseek-flash",
                "display_name": "DeepSeek V4.1 Flash",
                "capability": "text",
                "input_price_per_m": Decimal("0.30"),
                "output_price_per_m": Decimal("1.20"),
                "is_default": True,
            },
            {
                "model_key": "deepseek-v4-pro",
                "display_name": "DeepSeek V4 Pro",
                "capability": "text",
                "input_price_per_m": Decimal("1.32"),
                "output_price_per_m": Decimal("3.96"),
            },
        ],
    },
    "byteplus": {
        "name": "豆包（BytePlus ModelArk）",
        "base_url": "https://ark.ap-southeast.bytepluses.com/api/v3",
        "api_key_help": "在 BytePlus ModelArk 控制台的 API Key 管理頁建立，並先開通要使用的模型",
        "models": [
            {
                "model_key": "seed-2-0-lite-260228",
                "display_name": "Seed 2.0 Lite",
                "capability": "vision",
                "is_default": True,
            },
        ],
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_help": "在 https://openrouter.ai/keys 建立；模型名稱格式如 provider/model",
        "models": [],
    },
    "kie": {
        "name": "kie.ai",
        "base_url": "https://api.kie.ai",
        "api_key_help": "在 https://kie.ai 的 API Key 頁面建立。kie 的模型名稱就是網址路徑，例如 gemini-3-8-flash-openai",
        "models": [
            {
                "model_key": "gemini-3-8-flash-openai",
                "display_name": "Gemini 3.8 Flash",
                "capability": "vision",
                "is_default": True,
            },
        ],
    },
    "custom": {
        "name": "自訂（OpenAI 相容）",
        "base_url": "",
        "api_key_help": "任何提供 OpenAI 相容 /chat/completions 介面的服務",
        "models": [],
    },
}
