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
- 技術棧：FastAPI + PostgreSQL（pgvector）+ Redis + MinIO + FFmpeg，前端為手機優先 PWA，用 Docker Compose 部署在單台 VPS。

## 文件

- `docs/01-research.md`：調研
- `docs/02-architecture.md`：架構與資料模型
- `docs/03-vps-sizing.md`：VPS 規格
- `docs/04-roadmap.md`：執行方案、階段、成本
- `docs/05-server-setup.md`：伺服器初始化

## 正式伺服器

- QQG.NET 洛杉磯，6 核 / 12 GB，50 GB 系統碟 + 150 GB 資料碟，Ubuntu 24.04，IP `50.114.172.174`，沒有 DDoS 防護。
- 初始化：`infra/scripts/server-bootstrap.sh`（root）。資料碟掛在 `/data`，Docker 資料放在 `/data/docker`。
- 部署 / 更新：在專案根目錄執行 `bash infra/scripts/deploy.sh`（git pull → docker compose up --build --wait）。
- 壓測：`bash infra/bench/vps-bench.sh`

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
- [ ] 伺服器初始化（server-bootstrap.sh）與壓測
- [ ] Phase 0：基礎建設（Compose 全套服務、FastAPI 骨架、登入、`ai_provider` + `usage_ledger`、前端 PWA 骨架、Caddy HTTPS）
- [ ] 網域：使用者尚未提供；需要一筆 A 記錄指向伺服器 IP
