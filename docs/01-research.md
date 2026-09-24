# 01 · 調研：可參考 / 可複用的開源專案與 API

調研時間：2026-09。目的是確認哪些輪子可以直接用、哪些只能參考、哪些必須自己做。

## 1. 參考案例（使用者提供截圖）

「混剪矩陣智能體」的功能模組：帳號檔案、素材中心、鏡頭剪輯、音色管理、任務中心、作品庫、發佈帳號管理、發佈任務。

值得借鏡的設計：

- **帳號檔案（人設）**：門店名、行業、目標受眾、核心賣點、產品詳情。它是 AI 改寫文案的上下文，也用來匹配素材。
- **鏡頭模板**：按策略分為「人設型 / 流量型 / 成交型」，每個模板由 N 個「鏡頭文案」組成（例：主理人自我介紹 6 個鏡頭）。
- **一鍵改寫文案 → 按人設匹配素材 → 提交雲端混剪**。

我們要多做的差異點：**素材不是人工分資料夾，而是上傳後自動識別、分類、打標籤**，混剪時由系統按鏡頭語義自動挑素材。

## 2. 開源專案

### 2.1 AI 短影片生成 / 混剪

| 專案 | 用途 | 可借鏡之處 |
| --- | --- | --- |
| [harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)（MIT） | 主題 → LLM 文案 → TTS → 字幕 → 素材 → 合成 | 整條 pipeline 的參考實作（FastAPI + MoviePy/FFmpeg），有 REST API |
| [ddean2009/MoneyPrinterPlus](https://github.com/ddean2009/MoneyPrinterPlus) | 批量混剪 + 自動發佈抖音 / 快手 / 小紅書 / 視頻號 | 批量混剪策略、國內 TTS（阿里雲、騰訊雲）、本地 ASR（faster-whisper） |
| [linyqh/NarratoAI](https://github.com/linyqh/NarratoAI) | AI 解說 + 剪輯 | 用多模態模型理解畫面再產生解說 |
| [sunzhen668899-cyber/jianying-mixcut](https://github.com/sunzhen668899-cyber/jianying-mixcut) | 多源產品影片 AI 語義去重混剪，並產出剪映草稿 | 「語義去重 + 統一配音字幕 + 片頭片尾模板」和我們的場景最接近；剪映草稿可供人工微調 |
| [qhp940304/oka_ai_hunjian](https://github.com/qhp940304/oka_ai_hunjian) | 短影片矩陣混剪系統 | 產品形態參考 |
| [mutonby/openshorts](https://github.com/mutonby/openshorts)、[artbyjazi/autoclip](https://github.com/artbyjazi/autoclip) | 長片切短片、字幕、重新構圖 | Whisper 逐字時間戳字幕、9:16 自動重構圖 |
| [arseneHuot/awesome-ai-video](https://github.com/arseneHuot/awesome-ai-video) | 中文 AI 影片資源索引 | 持續追蹤新工具 |

### 2.2 素材分析

| 工具 | 用途 |
| --- | --- |
| [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | 鏡頭切換偵測，把長素材切成可用片段 |
| FFmpeg / ffprobe | 取得解析度、時長、旋轉、編碼；抽關鍵幀；轉碼成低碼率 proxy |
| faster-whisper | 語音轉文字（口播素材） |
| 多模態大模型（Qwen-VL / GPT / Claude / Gemini 等） | 看關鍵幀，產生描述與標籤：場景（車間 / 門店 / 產品特寫 / 人物口播）、主體、品質評分 |
| CLIP / 向量嵌入 + pgvector | 用「鏡頭文案」語義搜尋最匹配的素材片段，並做重複素材去重 |

### 2.3 上傳

| 工具 | 用途 |
| --- | --- |
| [tus 協議](https://tus.io/) + [tusd](https://github.com/tus/tusd) | 斷點續傳伺服器，可直接寫入 S3 相容儲存 |
| [Uppy](https://uppy.io/docs/tus/) | 前端上傳元件，支援 tus、手機相機 |

手機在工廠現場網路不穩，影片又大（1080p 約 60 MB/分鐘，4K 更大），**斷點續傳是必要的**。

### 2.4 發佈與評論管理

| 方案 | 覆蓋平台 | 說明 |
| --- | --- | --- |
| [Upload-Post API](https://docs.upload-post.com/) | TikTok、Instagram、YouTube、Facebook、X、LinkedIn、Threads、Pinterest 等 | 付費 SaaS。單一 API 發佈、排程、webhook、統一數據、**評論讀取 / 回覆 / 刪除**；有 [Python SDK](https://github.com/Upload-Post/upload-post-pip) |
| [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app)（AGPL-3.0） | 國際主流平台 | 自架排程工具。需自己向各平台申請開發者 App。AGPL 授權要注意：若修改後對外提供服務須開源 |
| [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload) | 抖音、小紅書、視頻號、快手、B 站、TikTok、YouTube | 用 Playwright 模擬瀏覽器登入上傳。**非官方**，平台改版就會壞，也有帳號風控風險 |
| [抖音開放平台](https://open.douyin.com/platform/resource/docs/ability/content-management/douyin-publish-solution) | 抖音 | 官方發佈 API；[評論管理](https://developer.open-douyin.com/capacity-center-page/capacity-detail/7180530418775490619)等能力需申請權限，企業號有更多權限 |
| [TikTok Content Posting API](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post) | TikTok | 免費，但**未通過審核前只能發私密影片**，且每 24 小時最多 5 個使用者 |

## 3. 結論

1. **混剪引擎自己做**：以 FFmpeg 為核心，參考 MoneyPrinterTurbo 的 pipeline。現成專案都是「關鍵字 → 圖庫素材」，而我們的核心是「使用者自己拍的素材 → 自動理解 → 按鏡頭挑選」，需要自研。
2. **素材理解用「規則 + 多模態模型 + 向量」三層**：ffprobe 和 PySceneDetect 做結構化切分，多模態模型做語義標籤，向量檢索做匹配與去重。
3. **發佈層做成 adapter 介面**：
   - 國際平台：先接 Upload-Post（最快上線，順帶取得評論管理），之後視成本改為自架或官方 API。
   - 國內平台：官方開放平台優先（抖音企業號）；Playwright 方案只作為過渡，並標示風險。
4. **先確定目標平台**：國內還是海外，會影響 VPS 機房位置、ICP 備案、要接哪些 API，是最優先要回答的問題。
