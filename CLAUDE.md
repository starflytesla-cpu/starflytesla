# CLAUDE.md

這是「Starfly 混剪矩陣平台」：給線下工廠 / 實體門店用的「手機隨手拍 → 素材自動識別分類 → AI 混剪成片 → 人工審核 → 發佈到海外社媒 → 評論管理」WebApp。

## 與使用者溝通

- **一律用繁體中文回覆**。使用者不是專職工程師：步驟要具體、一次一個指令，並說明預期會看到什麼。
- 需要使用者在自己電腦或網頁上操作時，要明確說出在哪裡操作、點哪裡。

## 已確定的決策（詳見 docs/04-roadmap.md）

- 目標平台：**海外**（TikTok / Instagram Reels / YouTube Shorts / Facebook Reels），發佈先接 Upload-Post API。
- 商業模式：先自營服務自己的客戶，從**一個帳號群**開始；之後打包銷售或改積分制，所以每個 AI / 渲染 / 發佈動作都要記錄成本（`usage_ledger`）。
- AI：文案用 DeepSeek，看圖打標籤用 kie.ai 的 Gemini 3.8 Flash（使用者 2026-10-01 指定；豆包 Seed Vision 為備選），配音用 kie.ai 的 Gemini 3.8 Flash TTS（使用者 2026-10-01 指定；ElevenLabs 經 kie 出現 Internal Error，保留為備選），備援用 OpenRouter。
- 成片和 AI 評論回覆**都要人工確認**後才發出。
- 技術棧：FastAPI + PostgreSQL（pgvector）+ FFmpeg；前端 React + Vite + Ant Design（手機優先 PWA）；Caddy 提供網頁與 HTTPS；Docker Compose 部署在單台 VPS。不使用 Redis 與 MinIO（見 docs/02-architecture.md 開頭）。

## 文件

- `docs/01-research.md`：調研
- `docs/02-architecture.md`：架構與資料模型
- `docs/03-vps-sizing.md`：VPS 規格
- `docs/04-roadmap.md`：執行方案、階段、成本
- `docs/05-server-setup.md`：伺服器初始化

## 程式結構與慣例

- `services/api/`：FastAPI。路由在 `app/routers/`，只處理輸入輸出；業務邏輯在 `app/services/`；資料表在 `app/models.py`，改資料表必須新增 Alembic 遷移（`alembic revision --autogenerate`）並用 `alembic check` 確認。
- API 回應一律是 `{code, data, msg, reason}`：成功用 `schemas.ok()`；失敗丟 `app.errors` 的 `AppError`，HTTP status 要反映真實失敗，`msg` 是可直接顯示的繁體中文。
- **所有 AI 呼叫都必須走 `app/services/ai_provider.py`**，才會寫入 `usage_ledger` 成本記錄。kie.ai 的特殊處理也在這裡：網址是 `{base}/{model_key}/v1/chat/completions`、預設串流要關掉、圖片要先經 kie 檔案上傳 API 換成網址。
- 渠道 API Key 用 `security.encrypt_secret` 加密存放，永遠不回傳給前端；上游網址要經過 `validate_upstream_url`（防 SSRF）。
- 背景任務：`app/services/tasks.py` 的 `enqueue` 排入 `tasks` 表，`app/worker.py`（`worker` 容器）領取執行；新任務類型在 `HANDLERS` 註冊。FFmpeg 呼叫集中在 `app/services/media.py`。
- 文案：`script_writer.py`（worker 任務 `script.generate`）組 prompt 與解析；內建模板在 `template_library.py`（改完重新部署即同步）；音色清單在 `voices.py`（Gemini 與 ElevenLabs 兩種引擎，`resolve_voice` 依配音模型換成可用音色）；試聽、音色樣本、成片配音快取都在 `speech.py`（`ai_provider.tts`）。
- 成片：`renderer.py`（worker 任務 `video.render`）負責挑素材、配音快取、ASS 字幕與渲染；長度一律以影格（30fps）計算，片段只輸出影像、聲音另做無損 WAV，最後由 `media.compose_final` 一次合成（不要再用 concat demuxer 串接含 AAC 的片段，會卡頓）；背景音樂在 `music.py`（上傳 / kie Suno 產生、`pick_for_video`）；API 邏輯在 `videos.py`；任務中心在 `task_center.py`。渲染用的 FFmpeg 指令同樣集中在 `media.py`。
- 素材檔案在 `MEDIA_ROOT`（容器內 `/media`），網址 `/media/{tenant}/assets|videos/{id}/...` 與 `/media/{tenant}/tts/...` 由 Caddy 經 `/api/media/auth` 檢查權限後直接提供。場景分類代碼在 `asset_analyzer.SCENES`，前端 `SCENE_LABELS` 要同步。
- `apps/web/`：API 只透過 `src/api/http.ts` 的 `http` 呼叫（唯一例外：上傳用 `src/api/upload.ts` 的 tus-js-client）；型別與端點集中在 `src/api/index.ts`；選單與後續功能預留頁在 `src/navigation.tsx`。
- 驗證：後端 `python -m pytest -q`（需要本機 PostgreSQL 的 `starfly_test` 資料庫與 ffmpeg）；前端 `npm run lint && npm run build`；CI 會在推送時自動跑。

## Linear 協作（與 Codex 共同開發）

- Codex 讀的是 `AGENTS.md`（內容指向本檔 + 協作流程）；改了共用規則時兩份都要對得上。
- Linear：Eilveiaan 團隊 → 專案「工廠混剪自動化 WebApp」（P-EIL-2，隸屬 SocialOps 社媒运营）。文件〈交接總覽（先讀這份）〉〈協作規範（Claude × Codex）〉；Milestones 對應 Phase 0～4。
- **EIL-5〈📒 Git 變更記錄〉**：每次推送後在這裡留言（commit hash、說明、影響範圍、注意事項、驗證結果）；開工前先讀最新留言、看 In Progress 的 Issue，再 `git pull --rebase`。設定 `LINEAR_API_KEY` Secret 後，`.github/workflows/linear-git-log.yml` 會自動貼 commit 清單。
- 每項工作對應一張 Issue，標籤 `Claude` / `Codex`，需要使用者動手的加 `待使用者操作`；commit 訊息結尾加 `(EIL-編號)`。
- 不要 force push、不要改寫已推送的歷史；Codex 新增 Alembic 遷移時注意 `down_revision` 維持單一 head。

## 正式伺服器

- QQG.NET 洛杉磯，6 核 / 12 GB，50 GB 系統碟 + 150 GB 資料碟，Ubuntu 24.04，IP `50.114.172.174`，沒有 DDoS 防護。
- 初始化：`infra/scripts/server-bootstrap.sh`（root）。資料碟掛在 `/data`，Docker 資料放在 `/data/docker`。
- 部署 / 更新：在專案根目錄執行 `bash infra/scripts/deploy.sh`（git pull → docker compose up --build --wait）。
- 壓測：`bash infra/bench/vps-bench.sh`

### Claude 操作伺服器的方式：GitHub Actions 維運通道（首選）

雲端開發環境不能直接 SSH 到伺服器，改用 `.github/workflows/ops.yml`：

- 用 GitHub MCP 的 `actions_run_trigger`（`run_workflow`，workflow `ops.yml`，ref `claude/exciting-fermi-nad1gj`，inputs `{"command": "..."}`）觸發，再用 `actions_list` / `get_job_logs` 讀結果。
- 可用指令只有 `infra/scripts/ops.sh` 定義的：`status`、`smoke`、`queue`（任務佇列 / 素材狀態 / 最近錯誤）、`logs <api|worker|web|postgres> [行數]`、`deploy`、`restart <api|worker|web>`。需要新的診斷能力時，修改 ops.sh（輸出不得包含密碼、`.env` 內容；IP / Email 要經過 `redact`），推送後經 CI 自動部署生效。
- 推送到 `claude/exciting-fermi-nad1gj` 且 CI 通過後，Ops 會自動執行 `deploy`（部署完會跑 `smoke`）。
- 需要使用者先在伺服器執行 `setup-ops.sh` 並設定 `OPS_HOST` / `OPS_KNOWN_HOSTS` / `OPS_SSH_KEY` 三個 Secrets；未設定時 workflow 會顯示警告並略過。
- 這台伺服器的主機商模板預設**關閉金鑰登入**（回應 `Permission denied (password)`），需在伺服器執行 `bash infra/scripts/enable-ssh-key.sh` 開啟（2026-09-30 已請使用者執行）。

### 從使用者的 Mac 操作伺服器

雲端開發環境無法連到伺服器；在使用者 Mac 上執行的 Claude Code 可以直接用 SSH 操作。

- 連線：`ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes root@50.114.172.174 '<指令>'`
- 金鑰登入可能還沒設定好（之前 ssh-copy-id 失敗過）。如果上面的指令回報 Permission denied，請使用者**自己在終端機**執行下面這行並輸入一次 root 密碼（Claude 的指令視窗無法輸入密碼）：
  `cat ~/.ssh/id_ed25519.pub | ssh -o PubkeyAuthentication=no root@50.114.172.174 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"`
- 伺服器上的專案在 `/root/starflytesla`。改程式碼一律在 Mac 端改好、commit、push 到 `claude/exciting-fermi-nad1gj`，再到伺服器執行 `cd /root/starflytesla && bash infra/scripts/deploy.sh`；不要直接在伺服器上改程式碼。
- 使用者曾在 Mac 上誤跑過 deploy.sh，Mac 上可能有一份本機部署。確認後可以用 `docker compose -f infra/docker-compose.yml down`（不要加 `-v`）停掉。

### 待處理問題

- **2026-09-30 登入卡住（已查明，不是程式問題）**：用維運通道查證，伺服器上經由 Caddy 登入 0.38 秒成功；後端記錄顯示使用者瀏覽器只送達過 2 次 `GET /api/auth/me`，`POST /api/auth/login` 從未到達。使用者流量來自 `137.175.62.129`（AS54600 PEG TECH 機房 IP），代表 Mac 開著 VPN / 代理，登入請求在代理那一段遺失。處理方式：請使用者關閉代理（或把伺服器 IP 設成直連）再試；長期用 HTTPS 避免中間設備干擾明文 HTTP。
- **2026-09-30 伺服器無法對外連線（已恢復）**：約 UTC 16:25～17:10 伺服器對外 TCP 全部逾時（ICMP 正常），伺服器約 17:11 重新開機後恢復；17:38 經維運通道自動部署 6e62ff2 成功（git pull、npm / pip 下載都正常）。若再發生，先用 `curl -sv https://1.1.1.1` 判斷是否 TCP 連線階段就逾時，是的話屬主機商網路問題。另外路徑 MTU 約 1448（1420 可通、1452 不通），目前未造成問題，之後若大檔上傳異常可考慮把 ens17 的 MTU 調到 1420。

### 在伺服器上操作時的規則

- **以下動作要先向使用者說明並取得同意**：格式化磁碟（`FORMAT_DATA_DISK=yes`）、關閉 SSH 密碼登入（`DISABLE_SSH_PASSWORD=yes`，必須先確認使用者的金鑰登入可用，否則會被鎖在外面）、修改防火牆、刪除資料或 Docker volume、重開機。
- 對外只開放 22 / 80 / 443。資料庫、Redis、MinIO 只綁定 127.0.0.1。
- 機密（密碼、API Key）只放在伺服器的 `.env`（權限 600）。

## 程式碼規則

- **這個 GitHub 倉庫是公開的**：絕對不能提交任何密碼、API Key、token、`.env`。
- 程式碼註解與文件使用繁體中文。
- Shell 腳本必須通過 `shellcheck -S warning`。

## 目前進度

- [x] 調研、架構、執行方案、VPS 選購
- [x] 伺服器初始化與壓測（2026-09-30）：steal 0%，30 秒成片約 30 秒渲染；專案 clone 在伺服器的 `/root/starflytesla`
- [x] Phase 0 程式完成（2026-09-30）：登入 / 帳號、模型渠道、`ai_provider` + `usage_ledger`、後台網頁、Caddy、deploy.sh 自動產生密碼
- [x] Phase 0 部署到正式伺服器（2026-09-30）
- [x] 登入卡住（使用者代理造成）與伺服器連外問題已解決，維運通道自動部署正常（2026-09-30）
- [ ] 用真實 API Key 測試 DeepSeek 與豆包
- [x] Phase 1 素材中心程式完成（2026-10-01）：tus 斷點續傳、worker（轉檔 / 切鏡頭 / 看圖模型標籤 / 重複偵測）、素材庫頁面
- [x] Phase 1 驗收通過（2026-10-01）：使用者實測上傳與 kie.ai Gemini 3.8 Flash 看圖標註成功
- [x] Phase 2 程式完成（2026-10-01）：帳號檔案、14 個內建模板、DeepSeek 多版本文案、ElevenLabs 音色試聽與綁定
- [ ] Phase 2 驗收：使用者用真實 DeepSeek 產生文案、試聽 kie.ai 配音
- [x] Phase 3 程式完成（2026-10-01）：自動挑素材、逐鏡頭配音（快取）、ASS 字幕、1080×1920 成片、作品庫審核與換素材、任務中心
- [ ] Phase 3 驗收：用真實素材與文案產生成片並審核（2026-10-01 使用者回報背景聲不一致與卡頓，已改為統一背景音樂與影格精確渲染，待重新驗收）
- [ ] 網域：使用者尚未提供；需要一筆 A 記錄指向伺服器 IP
