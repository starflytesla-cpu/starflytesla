# AGENTS.md（給 Codex 與其他 AI 開發助手）

這個專案由 **Claude 與 Codex 共同開發**。專案規則、架構、慣例、伺服器操作方式全部寫在 [`CLAUDE.md`](CLAUDE.md)，**那份同樣適用於你，請先完整讀過**。本檔只補充協作流程。

## 最重要的規則（摘自 CLAUDE.md）

- **一律用繁體中文**和使用者溝通、寫註解與文件。使用者不是專職工程師：步驟要具體、一次一個指令。
- **倉庫是公開的**：絕對不能提交密碼、API Key、token、`.env`，也不要貼到 Linear。
- 所有 AI 呼叫都走 `services/api/app/services/ai_provider.py`（寫入 `usage_ledger` 成本記錄）。
- API 回應一律 `{code, data, msg, reason}`；改資料表要新增 Alembic 遷移並跑 `alembic check`。
- 成片與 AI 評論回覆都要人工確認後才發出。

## 分支

- 共用分支：`claude/exciting-fermi-nad1gj`。**推送且 CI 通過後會自動部署到正式伺服器**。
- 推送前一律 `git pull --rebase origin claude/exciting-fermi-nad1gj`；不要 force push、不要改寫已推送的歷史。
- 大型或實驗性改動可以先開 `codex/<主題>` 分支，完成後 rebase 回共用分支。

## Linear：開發過程與交接都在這裡

- 專案：Linear → Eilveiaan 團隊 → 專案「工廠混剪自動化 WebApp」（P-EIL-2，隸屬 SocialOps 社媒运营）
- 先讀專案文件〈交接總覽（先讀這份）〉與〈協作規範（Claude × Codex）〉。
- **EIL-5〈📒 Git 變更記錄〉**：雙方的 git 變更都記在這裡。

### 每次工作的流程

1. 開工前：讀 EIL-5 最新留言、看 In Progress 的 Issue（避免和 Claude 同時改同一處），再 `git pull --rebase`。
2. 每項工作對應一張 Issue（沒有就建立），加標籤 `Codex`，開始時移到 In Progress。
3. Commit 訊息：`類型(範圍): 繁體中文說明 (EIL-編號)`，例如 `fix(render): 修正字幕溢出 (EIL-24)`。
4. 推送前必須通過：
   - 後端：`cd services/api && python -m pytest -q`（需要本機 PostgreSQL 的 `starfly_test` 資料庫與 ffmpeg）
   - 前端：`cd apps/web && npm run lint && npm run build`
   - Shell 腳本：`shellcheck -S warning`
5. 推送後：在 EIL-5 留言，格式如下；並更新 Issue 狀態（等使用者驗收用 In Review，完成用 Done）。

```
**[Codex] 推送到 claude/exciting-fermi-nad1gj**
- `abc1234` feat(xxx): 一句話說明 (EIL-n)

影響範圍：後端 / 前端 / 資料表遷移 / 部署
注意事項：例如「新增遷移 0009」「新增環境變數 XXX」
驗證：pytest 通過、lint / build 通過、CI ✅
```

如果你沒有 Linear 的存取權，至少要把 commit 訊息寫完整（含 EIL 編號）。設定了 `LINEAR_API_KEY` Secret 時，`.github/workflows/linear-git-log.yml` 會自動把每次推送的 commit 貼到 EIL-5。

### 核對對方的變更

- 用 `git log` 對照 EIL-5 的留言；發現沒記錄的 commit 就補一則「補記」留言。
- 發現 Claude 的改動有問題，在相關 Issue 留言說明；小修正可以直接改並在 EIL-5 說明，不要大改對方剛寫的程式。
- 改變了架構、慣例或進度時，同步更新 `CLAUDE.md` 與 Linear〈交接總覽〉。
