# 工廠混剪 WebApp：Codex 接手紀錄

核對日期：2026-10-05。使用者授權接手後續開發，並明確選擇「Upload-Post 尚未準備，先完成程式」；網域尚未設定。

## 已完整讀取的範圍

[Linear 專案](https://linear.app/eilveiaan/project/工廠混剪自動化-webapp-34206821f460)：專案說明與 7 個資源項目、2 份完整文件、5 個里程碑、20 張議題（包含已封存議題）的完整描述／關聯／附件清單／狀態歷史、全部 7 則議題留言。議題、文件、專案、里程碑留言的分頁均讀完；文件／專案／里程碑沒有留言，沒有專案 status update。議題附件只有 EIL-5 的 GitHub commit 歷史連結，無額外媒體附件。

已核對倉庫 AGENTS.md、CLAUDE.md、EIL-5 記錄與 Git。遠端部署分支仍為 `7535e93a19824b98da695b203747fc3cbb933982`，最新 CI 與 Ops 已成功；Ops 日誌包含該版本及服務 healthy。2026-10-05 只讀 GET /api/health 回應 HTTP 200，這項檢查不代表全部業務功能已驗收。

## 接手結論與順序

1. Phase 0–1 已有完成／驗收記錄，保留既有實作。
2. EIL-45 已有端點錯配查證：中國區方舟 Key 配到 BytePlus 國際版；待使用者在後台更正端點與 Model ID，不能因診斷程式已部署而標記問題已解決。
3. EIL-14、EIL-15 保留 In Review，尚無 Phase 2–3 的使用者通過驗收證據。
4. EIL-16 先完成發佈渠道基礎，再依序接 EIL-17 帳號對應、EIL-18 人工確認後的排程／回執恢復與成本、EIL-19 評論同步及人工確認回覆。不能把渠道測試當作發佈成功。
5. EIL-20（帳號／Key）與 EIL-21（網域）等待使用者準備；不購買方案、不使用真實 Key、不發佈貼文。
6. EIL-22 原來仍是 Todo，但 EIL-5 的自動留言與 Linear Git Log run 37173491332 已證明設定於 2026-10-04 生效，本次已修正為 Done；未讀取 Secret 的值。

## 本次程式交付

分支：`codex/eil-16-publishing-channel`，基線：`7535e93`。

- 新增發佈渠道頁與管理員 API，可先儲存無 Key 設定、更新、啟用／停用、清除 Key。
- 重用 `encrypt_secret`；前端只收到金鑰末 4 碼，金鑰格式檢查與上游錯誤處理避免洩漏憑證。
- 公網 HTTPS URL 檢查、每次請求前重新檢查 DNS、拒絕轉址，管理員與租戶隔離。
- 唯讀 `GET /api/uploadposts/me` 使用 `Authorization: Apikey`，只有上游明確 success 且方案有效才通過。結果持久化，更換 Key 或 Base URL 後清除舊檢查狀態。
- `usage_ledger` 新增發佈渠道關聯；查詢成功／失敗都有帳本紀錄，現有成本頁顯示渠道名稱。這次的帳號 GET 查詢為 0 成本；實際 `publish.post` 帳本與未知成本處理仍須隨 EIL-18 接入。
- Alembic `0009`，`down_revision=0008`，不改既有歷史遷移。

Upload-Post 契約來源：[Current User API](https://docs.upload-post.com/api/current-user/)。本次沒有建立任何外部貼文／評論。

## 驗證與交付邊界

- 完整後端 119 項通過，其中新增 32 項涵蓋加密、權限／租戶、SSRF、重新驗證 DNS、停用／清除、401／403／429／503、逾時、格式錯誤、錯誤不洩漏、帳本讀回，以及檢查期間更換 Key／停用時舊結果不能覆蓋新設定。
- `alembic check` 通過；`0008 → 0009 → 0008 → 0009` 升級／回復／再升級通過，既有租戶及成本紀錄讀回一致（包括未知成本 NULL）。前端 lint/build、Shellcheck 通過。
- 本地 UI fixture 操作通過：登入、無 Key 新增渠道、列表讀回；金鑰未設定時「檢查連線」維持停用。畫面檢查通過。
- 現有測試工具有 Starlette／httpx 棄用警告，前端有 bundle 大小警告；本次不更換相依或另做拆包。
- 本機 Homebrew FFmpeg 缺少 ASS 濾鏡；全套渲染驗證使用隔離環境內含 libass 的 FFmpeg。未改應用渲染邏輯或相依清單。
- 本機代理把 Upload-Post 解析到 `198.18.x.x`，正式防護會拒絕；UI 檢查使用獨立合成資料庫與 DNS fixture，與後端 SSRF 測試分開記錄。
- GitHub CLI（EthanLuang）與 Connector（loyaraisupport-max）皆沒有原倉庫 push 權限。fork：`EthanLuang/starflytesla`，以草稿 PR 交付，不推送部署分支。
- 正式部署仍須精確比較伺服器現況、備份、確認遷移與回復程序，以及部署後實際讀回；此文件不能當成部署或使用者驗收證據。

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
| [EIL-16](https://linear.app/eilveiaan/issue/EIL-16/phase-4-1接入-upload-post-api渠道設定成本記錄) | Phase 4-1：接入 Upload-Post API（渠道設定、成本記錄） | In Progress（Codex，渠道基礎） |
| [EIL-17](https://linear.app/eilveiaan/issue/EIL-17/phase-4-2發佈帳號管理tiktok-ig-youtube-fb-綁定) | Phase 4-2：發佈帳號管理（TikTok / IG / YouTube / FB 綁定） | Todo |
| [EIL-18](https://linear.app/eilveiaan/issue/EIL-18/phase-4-3排程發佈審核通過的成片-指定帳號時間) | Phase 4-3：排程發佈（審核通過的成片 → 指定帳號、時間） | Todo |
| [EIL-19](https://linear.app/eilveiaan/issue/EIL-19/phase-4-4評論管理抓取評論ai-建議回覆人工確認後送出) | Phase 4-4：評論管理（抓取評論、AI 建議回覆、人工確認後送出） | Todo |
| [EIL-20](https://linear.app/eilveiaan/issue/EIL-20/待使用者註冊-upload-post-帳號並取得-api-key) | 【待使用者】註冊 Upload-Post 帳號並取得 API Key | Todo |
| [EIL-21](https://linear.app/eilveiaan/issue/EIL-21/待使用者網域與-https) | 【待使用者】網域與 HTTPS | Todo |
| [EIL-22](https://linear.app/eilveiaan/issue/EIL-22/待使用者選用設定-linear-api-key讓每次推送自動記錄到-linear) | 【待使用者】（選用）設定 LINEAR_API_KEY，讓每次推送自動記錄到 Linear | Done（已核對自動記錄） |
| [EIL-23](https://linear.app/eilveiaan/issue/EIL-23/建立-claude-codex-協作機制agentsmdlinear-規範git-自動記錄) | 建立 Claude × Codex 協作機制（AGENTS.md、Linear 規範、git 自動記錄） | Done |
| [EIL-45](https://linear.app/eilveiaan/issue/EIL-45/豆包byteplus渠道測試失敗http-401-the-api-key-doesnt-exist) | 豆包（BytePlus）渠道測試失敗：HTTP 401 The API key doesn't exist | In Review |
