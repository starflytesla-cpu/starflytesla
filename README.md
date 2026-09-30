# Starfly 混剪矩陣平台（暫定名）

給線下工廠 / 實體門店用的「隨手拍 → 自動整理 → AI 混剪 → 多平台發佈 → 評論管理」一站式 WebApp。

> 狀態：**Phase 0 程式完成**（登入、帳號、模型渠道、成本記錄、後台網頁、部署），下一步是 Phase 1 素材中心。見 [docs/04-roadmap.md](docs/04-roadmap.md)。
>
> 方向：海外社媒（TikTok / IG / YouTube / FB）· 先自營一個帳號群 · 成片人工審核後發佈 · AI 使用 DeepSeek、豆包、kie.ai、OpenRouter。

## 核心流程

```
手機隨手拍 ──► 上傳（斷點續傳）──► 素材自動識別 / 分類 / 打標籤
                                         │
          帳號檔案（人設、賣點）──► AI 改寫鏡頭文案 ──► 挑素材 + 配音 + 字幕 + BGM
                                         │
                                  FFmpeg 批量渲染成片
                                         │
                     發佈管理（排程 / 多帳號 / 多平台）──► 評論管理 / 數據回收
```

## 文件

| 文件 | 內容 |
| --- | --- |
| [docs/01-research.md](docs/01-research.md) | GitHub 與網路調研：可參考 / 可複用的開源專案與 API |
| [docs/02-architecture.md](docs/02-architecture.md) | 系統架構、技術選型、模組拆分、資料模型草稿 |
| [docs/03-vps-sizing.md](docs/03-vps-sizing.md) | VPS 配置建議（入門 / 推薦 / 上限）與容量估算 |
| [docs/04-roadmap.md](docs/04-roadmap.md) | 執行方案 v1：已確定的決策、AI 分工、分階段計畫、成本估算、風險 |
| [docs/05-server-setup.md](docs/05-server-setup.md) | 伺服器初始化與部署：一行指令初始化、壓測、部署更新 |

## 目錄結構

```
apps/web/          前端（React + Vite + Ant Design，手機優先 PWA），正式環境由 Caddy 提供
services/api/      後端 API（FastAPI + SQLAlchemy + Alembic）
infra/             docker-compose.yml、部署 / 初始化 / 壓測腳本
docs/              規劃文件
```

## 部署

在伺服器上：`bash infra/scripts/deploy.sh`，詳見 [docs/05-server-setup.md](docs/05-server-setup.md)。

## 本機開發

需要 Python 3.12、Node 22、PostgreSQL 16。

```bash
# 後端（services/api）
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://starfly:starfly@localhost:5432/starfly SECRET_KEY=dev \
       ADMIN_EMAIL=admin@starfly.local ADMIN_PASSWORD=dev-password
alembic upgrade head && uvicorn app.main:app --reload --port 8000
python -m pytest -q          # 測試使用 starfly_test 資料庫

# 前端（apps/web），/api 會轉給 localhost:8000
npm install && npm run dev
```
