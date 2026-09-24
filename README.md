# Starfly 混剪矩陣平台（暫定名）

給線下工廠 / 實體門店用的「隨手拍 → 自動整理 → AI 混剪 → 多平台發佈 → 評論管理」一站式 WebApp。

> 狀態：**執行方案 v1 已確定**（見 [docs/04-roadmap.md](docs/04-roadmap.md)），下一步是 Phase 0 基礎建設。
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

## 目錄結構（規劃）

```
apps/web/          前端 WebApp（手機優先 PWA：拍攝上傳、素材庫、模板、任務、發佈）
services/api/      後端 API（FastAPI）：帳號、素材、模板、任務、發佈、評論
services/worker/   背景任務：素材分析、文案生成、TTS、渲染、發佈
infra/             Docker Compose、反向代理、部署腳本
docs/              規劃文件
```

## 本機啟動基礎設施

目前只有基礎服務（PostgreSQL + Redis + MinIO）可以啟動：

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml --env-file .env up -d
```
