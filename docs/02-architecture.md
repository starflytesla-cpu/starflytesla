# 02 · 系統架構（草稿）

## 1. 總覽

```
┌────────────── 手機 / 電腦瀏覽器（PWA）──────────────┐
│ 拍攝上傳 │ 素材庫 │ 帳號檔案 │ 模板 │ 任務 │ 作品 │ 發佈 │ 評論 │
└───────┬──────────────────────┬──────────────────────┘
        │ tus 斷點續傳          │ REST / WebSocket
        ▼                      ▼
   ┌─────────┐          ┌──────────────┐
   │  tusd   │──hook──► │  API (FastAPI)│
   └────┬────┘          └──────┬───────┘
        │                      │ 投遞任務
        ▼                      ▼
 ┌─────────────┐        ┌─────────────┐      ┌──────────────────┐
 │ 物件儲存     │◄──────►│ Redis 佇列   │─────►│ Workers           │
 │ MinIO / S3  │        └─────────────┘      │ ├ analyze 素材分析 │
 └─────────────┘                             │ ├ script  文案生成 │
        ▲                                    │ ├ tts     配音     │
        │                                    │ ├ render  渲染     │
 ┌──────┴──────┐                             │ └ publish 發佈/評論│
 │ PostgreSQL  │◄────────────────────────────└──────────────────┘
 │ + pgvector  │                                   │
 └─────────────┘                          外部：LLM / 多模態 / TTS / 社媒 API
```

Caddy 做反向代理並自動申請 HTTPS 憑證，全部服務用 Docker Compose 部署在單台 VPS；之後再按需求把 render worker 拆到獨立機器。

## 2. 技術選型

| 層 | 選擇 | 理由 |
| --- | --- | --- |
| 前端 | Next.js（或 Vue 3 + Vite）+ Tailwind，PWA | 手機優先；`<input capture>` 直接調用相機；可「加到主畫面」 |
| 上傳 | Uppy + tusd | 斷點續傳，直接寫入 S3 相容儲存 |
| API | Python FastAPI | 影片 / AI 生態都在 Python，和 worker 共用程式碼與模型 |
| 任務佇列 | Celery 或 Dramatiq + Redis | 分佇列：`analyze` / `render` / `publish` 各自限制併發 |
| 資料庫 | PostgreSQL 16 + pgvector | 業務資料和向量檢索放同一個庫，維運簡單 |
| 物件儲存 | MinIO（自架）或 Cloudflare R2 / 阿里雲 OSS | 素材量成長快，建議之後遷到雲端物件儲存 |
| 影片處理 | FFmpeg、PySceneDetect、faster-whisper | 成熟、可控、無授權費 |
| AI | 文案：DeepSeek；看圖打標籤：豆包 Seed Vision（BytePlus ModelArk）；備援：OpenRouter | 都是 OpenAI 相容介面，統一由 `ai_provider` 模組管理，可以切換廠商 |
| TTS | kie.ai（ElevenLabs 多語系）；Edge-TTS（免費 fallback） | 海外受眾，配音品質優先；音色管理模組對應這一層 |
| 部署 | Docker Compose + Caddy | 單台 VPS 即可運作 |

## 3. 核心模組

### 3.1 素材攝取與識別（差異化核心）

上傳完成 → tusd hook 通知 API → 建立 `asset` → 投遞 `analyze` 任務：

1. `ffprobe`：時長、解析度、方向、fps、是否有音軌。
2. 轉碼：產生 720p proxy（預覽和渲染草稿用）與縮圖。
3. `PySceneDetect`：切出片段 `clip`（例：一段 60 秒的車間影片切成 8 個鏡頭）。
4. 每個 clip 抽 1～3 張關鍵幀 → 多模態模型輸出結構化 JSON：
   `{scene: 車間|門店|產品特寫|人物口播|包裝出貨|..., subjects: [...], description, quality: 1-5, shaky, dark}`
5. 有人聲的 clip → faster-whisper 轉文字。
6. 產生嵌入向量寫入 pgvector；和既有素材比對，標記重複或近似素材。
7. 依規則與標籤自動歸入分類（可人工修正，修正結果回饋給規則）。

### 3.2 帳號檔案與文案

- 帳號檔案：品牌 / 門店、行業、受眾、賣點、產品詳情、口吻。
- 模板：策略（人設 / 流量 / 成交）→ 模板 → 鏡頭列表；每個鏡頭有「文案要點 + 期望畫面類型 + 時長」。
- LLM 按帳號檔案改寫每個鏡頭的文案，同時產出多個版本，供矩陣號使用，避免內容重複。

### 3.3 混剪引擎

輸入是一份 **時間軸 JSON**（鏡頭 → 文案 → 素材 clip → 配音 → 字幕 → 轉場 → BGM）：

1. 每個鏡頭用「期望畫面類型 + 文案語義」向量檢索候選 clip，排除近期用過的素材，按品質分數排序。
2. TTS 產生配音，並以配音長度決定鏡頭時長。
3. 字幕：直接使用 TTS 的時間戳，或用 whisper 對齊，輸出 ASS 花字。
4. FFmpeg `filter_complex` 一次合成：裁切成 9:16、調色、轉場、字幕、BGM 混音。
5. 去重策略（矩陣號必要）：同一模板產出 N 支影片時，素材組合、鏡頭順序、BGM、字幕樣式、輕微縮放 / 鏡像都做隨機化。

時間軸 JSON 也可以匯出成剪映草稿，供需要人工微調的客戶使用（參考 jianying-mixcut）。

### 3.4 發佈與評論

```python
class PublisherAdapter(Protocol):
    def publish(self, account, video, caption, schedule_at) -> PublishResult: ...
    def fetch_comments(self, account, post_id) -> list[Comment]: ...
    def reply_comment(self, account, comment_id, text) -> None: ...
```

第一個實作是 `UploadPostAdapter`（TikTok、IG、YouTube、FB）。之後視成本改接各平台官方 API，只需要新增 adapter。

評論管理：定時拉取評論 → LLM 分類（詢價 / 好評 / 投訴 / 垃圾）→ 產生建議回覆 → **人工確認後才送出**（初期不做自動回覆）。

### 3.5 人工審核流程

```
渲染完成 → pending_review ──通過──► approved → 排程 → published
                     └─退回（原因）─► rejected → 換素材 / 改文案 → 重新渲染
```

### 3.6 成本記錄（為積分制準備）

每一次 AI 呼叫、TTS、渲染、發佈都寫入 `usage_ledger`，記錄動作類型、用量、實際成本和所屬租戶與任務。試營運期只記錄不扣費；商品化時依實際成本訂定積分價格，加上 `credit_balance` 與儲值即可。

## 4. 資料模型（草稿）

```
tenant(id, name)                                  # 一個工廠 / 門店 = 一個租戶
user(id, tenant_id, role)
brand_profile(id, tenant_id, name, industry, audience, selling_points, details, tone, target_language)
asset(id, tenant_id, storage_key, duration, width, height, status, uploaded_by)
clip(id, asset_id, start, end, scene, tags[], description, quality, transcript, embedding vector)
template(id, tenant_id?, strategy, name)          # tenant_id 為空 = 系統內建行業模板
template_shot(id, template_id, order, brief, expected_scene, target_seconds)
job(id, tenant_id, template_id, profile_id, variants, status)
video(id, job_id, timeline_json, storage_key, status, reviewed_by, review_note)   # status 含 pending_review / approved / rejected
account_group(id, tenant_id, profile_id, name)   # 帳號群：一份人設 + 多個社媒帳號
social_account(id, tenant_id, account_group_id, platform, provider_profile, credentials_ref, status)
post(id, video_id, social_account_id, caption, schedule_at, status, remote_id, url)
comment(id, post_id, remote_id, author, text, intent, suggested_reply, reply_text, replied_by, replied_at)
usage_ledger(id, tenant_id, job_id?, action, provider, model, units, unit, cost_usd, created_at)
```

## 5. 安全與合規重點

- 社媒 token / cookie 加密儲存（`credentials_ref` 指向加密後的 secret），不寫入日誌。
- 多租戶隔離：所有查詢都要帶 `tenant_id`；物件儲存路徑加上租戶前綴。
- 上傳限制檔案類型與大小；對上傳檔案用 ffprobe 驗證，不信任前端提供的 MIME。
- AI 配音等生成內容，發佈時依各平台規定標示。
- 目標平台為海外，VPS 放在海外機房，不需要 ICP 備案。
