# CLAUDE.md

這是「Starfly 混剪矩陣平台」：給線下工廠 / 實體門店用的「手機隨手拍 → 素材自動識別分類 → AI 混剪成片 → 人工審核 → 發佈到海外社媒 → 評論管理」WebApp。

## 與使用者溝通

- **一律用繁體中文回覆**。使用者不是專職工程師：步驟要具體、一次一個指令，並說明預期會看到什麼。
- 需要使用者在自己電腦或網頁上操作時，要明確說出在哪裡操作、點哪裡。

## 已確定的決策（詳見 docs/04-roadmap.md）

- 目標平台：**海外**（TikTok / Instagram Reels / YouTube Shorts / Facebook Reels），發佈先接 Upload-Post API。
- 商業模式：先自營服務自己的客戶，從**一個帳號群**開始；之後打包銷售或改積分制，所以每個 AI / 渲染 / 發佈動作都要記錄成本（`usage_ledger`）。
- AI：文案用 DeepSeek，看圖打標籤用豆包 Seed Vision（BytePlus），配音用 kie.ai（ElevenLabs），備援用 OpenRouter。
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
- **所有 AI 呼叫都必須走 `app/services/ai_provider.py`**，才會寫入 `usage_ledger` 成本記錄。
- 渠道 API Key 用 `security.encrypt_secret` 加密存放，永遠不回傳給前端；上游網址要經過 `validate_upstream_url`（防 SSRF）。
- `apps/web/`：API 只透過 `src/api/http.ts` 的 `http` 呼叫；型別與端點集中在 `src/api/index.ts`；選單與後續功能預留頁在 `src/navigation.tsx`。
- 驗證：後端 `python -m pytest -q`（需要本機 PostgreSQL 的 `starfly_test` 資料庫）；前端 `npm run lint && npm run build`；CI 會在推送時自動跑。

## 正式伺服器

- QQG.NET 洛杉磯，6 核 / 12 GB，50 GB 系統碟 + 150 GB 資料碟，Ubuntu 24.04，IP `50.114.172.174`，沒有 DDoS 防護。
- 初始化：`infra/scripts/server-bootstrap.sh`（root）。資料碟掛在 `/data`，Docker 資料放在 `/data/docker`。
- 部署 / 更新：在專案根目錄執行 `bash infra/scripts/deploy.sh`（git pull → docker compose up --build --wait）。
- 壓測：`bash infra/bench/vps-bench.sh`

### 從使用者的 Mac 操作伺服器

雲端開發環境無法連到伺服器；在使用者 Mac 上執行的 Claude Code 可以直接用 SSH 操作。

- 連線：`ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes root@50.114.172.174 '<指令>'`
- 金鑰登入可能還沒設定好（之前 ssh-copy-id 失敗過）。如果上面的指令回報 Permission denied，請使用者**自己在終端機**執行下面這行並輸入一次 root 密碼（Claude 的指令視窗無法輸入密碼）：
  `cat ~/.ssh/id_ed25519.pub | ssh -o PubkeyAuthentication=no root@50.114.172.174 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"`
- 伺服器上的專案在 `/root/starflytesla`。改程式碼一律在 Mac 端改好、commit、push 到 `claude/exciting-fermi-nad1gj`，再到伺服器執行 `cd /root/starflytesla && bash infra/scripts/deploy.sh`；不要直接在伺服器上改程式碼。
- 使用者曾在 Mac 上誤跑過 deploy.sh，Mac 上可能有一份本機部署。確認後可以用 `docker compose -f infra/docker-compose.yml down`（不要加 `-v`）停掉。

### 待處理問題

- **2026-09-30 登入卡住**：正式伺服器部署完成，`http://50.114.172.174` 的登入頁可以開啟，但按「登入」後一直轉圈。登入頁能出現，推測 `GET /api/auth/me` 有回應，`POST /api/auth/login` 則沒有回應（尚未證實）。排查順序：
  1. `docker compose -f infra/docker-compose.yml ps` 以及 `logs --tail 100 api web`
  2. 在伺服器上用 curl 打 `http://localhost/api/auth/login`（密碼在 `.env` 的 `ADMIN_PASSWORD`），確認後端本身是否正常
  3. 使用者人在美國，可以排除跨境網路干擾；問題應該在伺服器端（容器狀態、API 是否卡住、Caddy 轉發、資料庫連線）。若伺服器本機 curl 也卡住，查 api 容器記錄與 `docker compose exec api python -c ...` 逐步縮小範圍。
  4. 還沒有網域時，可以先用免費的 `50-114-172-174.sslip.io`（自動解析到伺服器 IP）當 `SITE_ADDRESS`，Caddy 會自動申請 Let's Encrypt 憑證，網站就有 HTTPS。修改前先跟使用者確認。

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
- [ ] 解決登入卡住（見「待處理問題」），再用真實 API Key 測試 DeepSeek 與豆包
- [ ] Phase 1：素材中心
- [ ] 網域：使用者尚未提供；需要一筆 A 記錄指向伺服器 IP
