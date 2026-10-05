# 工廠混剪 WebApp：Codex 接手紀錄

核對日期：2026-10-05。使用者授權接手後續開發，並明確選擇「Upload-Post 尚未準備，先完成程式」；網域尚未設定。

## 已完整讀取的範圍

[Linear 專案](https://linear.app/eilveiaan/project/工廠混剪自動化-webapp-34206821f460)：專案說明與 7 個資源項目、2 份完整文件、5 個里程碑、20 張議題（包含已封存議題）的完整描述／關聯／附件清單／狀態歷史、全部 7 則議題留言。議題、文件、專案、里程碑留言的分頁均讀完；文件／專案／里程碑沒有留言，沒有專案 status update。議題附件只有 EIL-5 的 GitHub commit 歷史連結，無額外媒體附件。

已核對倉庫 AGENTS.md、CLAUDE.md、EIL-5 記錄與 Git。遠端部署分支仍為 `7535e93a19824b98da695b203747fc3cbb933982`，最新 CI 與 Ops 已成功；Ops 日誌包含該版本及服務 healthy。2026-10-05 只讀 GET /api/health 回應 HTTP 200，這項檢查不代表全部業務功能已驗收。

## 接手結論與順序

1. Phase 0–1 已有完成／驗收記錄，保留既有實作。
2. EIL-45 已有端點錯配查證：中國區方舟 Key 配到 BytePlus 國際版；待使用者在後台更正端點與 Model ID，不能因診斷程式已部署而標記問題已解決。
3. EIL-14、EIL-15 保留 In Review，尚無 Phase 2–3 的使用者通過驗收證據。
4. EIL-16～19 程式與本地驗證完成，交付草稿 PR，保留 In Review。渠道檢查、合成回執與測試通過均不能當作真實發佈成功。
5. EIL-20（帳號／Key）與 EIL-21（網域）等待使用者準備；不購買方案、不使用真實 Key、不發佈貼文。
6. EIL-22 原來仍是 Todo，但 EIL-5 的自動留言與 Linear Git Log run 37173491332 已證明設定於 2026-10-04 生效，本次已修正為 Done；未讀取 Secret 的值。

## 本次程式交付

分支：`codex/eil-16-publishing-channel`，基線：`7535e93`。交付：[草稿 PR #1](https://github.com/starflytesla-cpu/starflytesla/pull/1)，head 在 fork `EthanLuang/starflytesla`。原部署分支沒有推送。

- 新增發佈渠道頁與管理員 API，可先儲存無 Key 設定、更新、啟用／停用、清除 Key。
- 重用 `encrypt_secret`；前端只收到金鑰末 4 碼，金鑰格式檢查與上游錯誤處理避免洩漏憑證。
- 公網 HTTPS URL 檢查、每次請求前重新檢查 DNS、拒絕轉址，管理員與租戶隔離。
- 唯讀 `GET /api/uploadposts/me` 使用 `Authorization: Apikey`，只有上游明確 success 且方案有效才通過。結果持久化，更換 Key 或 Base URL 後清除舊檢查狀態。
- 帳號管理：讀取 Upload-Post profile／平台授權，驗證遠端帳號 ID，再對應本地帳號檔案。官方管理入口負責 profile 建立／OAuth；本地頁可停用、重查授權，目的地變更會阻擋既有任務。
- 發佈清單：只能選已人工審核的成片及同帳號檔案的社媒帳號，可用既有 DeepSeek 產生文案，修改後再人工確認。具時區的排程、持久化 UUID、防同成片／帳號重複、取消未執行任務；已排程影片不能換素材、重新渲染或刪除。
- 發佈 worker：執行前重查審核、檔案 SHA-256、帳號授權與目的地。對外 POST 前提交 `submitting` 與帳本；逾時、503、無法解析回執或工作中斷，只查原任務。明確拒絕的 429 可有限重試；公開貼文須有成功證據與 ID／網址，TikTok 收件匣草稿另記狀態。
- 評論收件匣：每 10 分鐘同步最近 30 天已公開貼文，分頁／去重／cursor／錯誤保留；未回覆、負面篩選及詢價提示。可手動生成 AI 建議，或明確開啟帳號的背景付費建議（預設關閉）。建議不自動送出，人工修改與確認才建立回覆；未知回執禁止重送。
- 成本：發佈與回覆連結渠道、貼文、評論；AI 文案／建議沿用 `ai_provider`。pending／uncertain 與未知費用 NULL 可在成本頁讀回，不以零成本掩蓋上游不確定結果。唯讀渠道 GET 才記 0 成本。
- Alembic `0009 → 0010`，基線 `0008`，不改既有歷史遷移；新增 `PublishChannel`、`SocialAccount`、`Post`、`Comment` 與帳本關聯。

Upload-Post 契約來源：[官方 API 文件](https://docs.upload-post.com/)、[Current User API](https://docs.upload-post.com/api/current-user/)。本次所有供應商操作驗證使用 mock／合成回執，沒有真實付費生成、對外貼文或評論回覆。

## 驗證與交付邊界

- 完整後端 **162 項通過**（112.25 秒）：既有 87 項、新增渠道 32 項、發佈／評論 43 項。新增檢查涵蓋加密、租戶／管理員權限、SSRF、DNS、並發設定變更、固定目的地與審核、防重複提交、工作中斷與回執不明只能查詢、429、安全錯誤、TikTok 草稿、評論分頁與去重、版本確認、背景 AI 開關／費用／不確定時不重試、人工回覆與成本讀回。
- `alembic check` 與 single head 通過；`0008 → 0010 → 0008 → 0010` 升級／回復／再升級通過，既有租戶、加密資料與成本紀錄讀回一致（包括未知成本 NULL）。前端 lint/build、Shellcheck 通過。
- 本地 UI fixture 操作通過：登入、無 Key 新增渠道與讀回、金鑰缺少時檢查停用、遠端帳號驗證／綁定、未人工確認不能排程或回覆、確認後排程／合成評論回覆持久化。沒有啟動發佈 worker；影片預覽的本地 fixture 未驗證播放，渲染由完整後端 FFmpeg 測試驗證。
- 現有測試工具有 Starlette／httpx 棄用警告，前端有 bundle 大小警告；本次不更換相依或另做拆包。
- 本機 Homebrew FFmpeg 缺少 ASS 濾鏡；全套渲染驗證使用隔離環境內含 libass 的 FFmpeg。未改應用渲染邏輯或相依清單。
- 本機代理把 Upload-Post 解析到 `198.18.x.x`，正式防護會拒絕；UI 檢查使用獨立合成資料庫與 DNS fixture，與後端 SSRF 測試分開記錄。
- GitHub CLI（EthanLuang）與 Connector（loyaraisupport-max）皆沒有原倉庫 push 權限。fork 草稿 PR 的 GitHub CI 尚無通過證據；以上是本地檢查結果。
- 排程共用既有 worker，指定時間是最早執行時間，渲染同時執行的延遲仍需真實週期驗收。背景評論同步需要 worker 持續運作與平台授權；TikTok 評論依遠端帳號 capability 放行。
- 正式部署仍須逐檔比較伺服器、保存可恢復備份、確認遷移與部署後讀回。測試證明既有資料可經過 up/down/up；downgrade 會刪除新增功能的資料表，使用後回滾必須先備份新貼文／評論資料或恢復部署前快照，不能把 downgrade 當作新資料無損回復。

## 全部議題索引

| 議題 | 內容 | 接手後狀態 |
| --- | --- | --- |
| [EIL-5](https://linear.app/eilveiaan/issue/EIL-5/git-變更記錄claude-codex-共用每次推送都要記) | 📒 Git 變更記錄（Claude × Codex 共用，每次推送都要記） | In Progress |
| [EIL-6](https://linear.app/eilveiaan/issue/EIL-6/phase-0後端後台網頁docker-部署維運通道) | Phase 0：後端、後台網頁、Docker 部署、維運通道 | Done |
| [EIL-7](https://linear.app/eilveiaan/issue/EIL-7/排查登入卡住伺服器無法對外連線) | 排查：登入卡住、伺服器無法對外連線 | Done |
| [EIL-8](https://linear.app/eilveiaan/issue/EIL-8/phase-1素材中心斷點續傳切鏡頭ai-標籤重複偵測) | Phase 1：素材中心（斷點續傳、切鏡頭、AI 標籤、重複偵測） | Done |
| [EIL-9](https://linear.app/eilveiaan/issue/EIL-9/看圖模型改用-kieai-gemini-38-flash) | 看圖模型改用 kie.ai Gemini 3.8 Flash | Done |
| [EIL-10](https://linear.app/eilveiaan/issue/EIL-10/phase-2帳號檔案14-個內建模板deepseek-多版本文案音色管理) | Phase 2：帳號檔案、14 個內建模板、DeepSeek 多版本文案、音色管理 | Done |
| [EIL-11](https://linear.app/eilveiaan/issue/EIL-11/配音改用-kieai-gemini-38-flash-ttselevenlabs-經-kie-出現-internal-error) | 配音改用 kie.ai Gemini 3.8 Flash TTS（ElevenLabs 經 kie 出現 Internal Error） | Done |
| [EIL-12](https://linear.app/eilveiaan/issue/EIL-12/phase-3混剪引擎作品庫審核任務中心) | Phase 3：混剪引擎、作品庫審核、任務中心 | Done |
| [EIL-13](https://linear.app/eilveiaan/issue/EIL-13/修正成片卡頓與背景聲不一致新增背景音樂庫) | 修正成片卡頓與背景聲不一致，新增背景音樂庫 | Done |
| [EIL-14](https://linear.app/eilveiaan/issue/EIL-14/待使用者phase-2-驗收真實-deepseek-文案試聽-gemini-配音) | 【待使用者】Phase 2 驗收：真實 DeepSeek 文案、試聽 Gemini 配音 | In Review |
| [EIL-15](https://linear.app/eilveiaan/issue/EIL-15/待使用者phase-3-重新驗收卡頓與背景音樂修正) | 【待使用者】Phase 3 重新驗收：卡頓與背景音樂修正 | In Review |
| [EIL-16](https://linear.app/eilveiaan/issue/EIL-16/phase-4-1接入-upload-post-api渠道設定成本記錄) | Phase 4-1：接入 Upload-Post API（渠道設定、成本記錄） | In Review（程式完成，未部署／真實驗收） |
| [EIL-17](https://linear.app/eilveiaan/issue/EIL-17/phase-4-2發佈帳號管理tiktok-ig-youtube-fb-綁定) | Phase 4-2：發佈帳號管理（TikTok / IG / YouTube / FB 綁定） | In Review（程式完成，未部署／真實驗收） |
| [EIL-18](https://linear.app/eilveiaan/issue/EIL-18/phase-4-3排程發佈審核通過的成片-指定帳號時間) | Phase 4-3：排程發佈（審核通過的成片 → 指定帳號、時間） | In Review（程式完成，未部署／真實驗收） |
| [EIL-19](https://linear.app/eilveiaan/issue/EIL-19/phase-4-4評論管理抓取評論ai-建議回覆人工確認後送出) | Phase 4-4：評論管理（抓取評論、AI 建議回覆、人工確認後送出） | In Review（程式完成，未部署／真實驗收） |
| [EIL-20](https://linear.app/eilveiaan/issue/EIL-20/待使用者註冊-upload-post-帳號並取得-api-key) | 【待使用者】註冊 Upload-Post 帳號並取得 API Key | Todo |
| [EIL-21](https://linear.app/eilveiaan/issue/EIL-21/待使用者網域與-https) | 【待使用者】網域與 HTTPS | Todo |
| [EIL-22](https://linear.app/eilveiaan/issue/EIL-22/待使用者選用設定-linear-api-key讓每次推送自動記錄到-linear) | 【待使用者】（選用）設定 LINEAR_API_KEY，讓每次推送自動記錄到 Linear | Done（已核對自動記錄） |
| [EIL-23](https://linear.app/eilveiaan/issue/EIL-23/建立-claude-codex-協作機制agentsmdlinear-規範git-自動記錄) | 建立 Claude × Codex 協作機制（AGENTS.md、Linear 規範、git 自動記錄） | Done |
| [EIL-45](https://linear.app/eilveiaan/issue/EIL-45/豆包byteplus渠道測試失敗http-401-the-api-key-doesnt-exist) | 豆包（BytePlus）渠道測試失敗：HTTP 401 The API key doesn't exist | In Review |
