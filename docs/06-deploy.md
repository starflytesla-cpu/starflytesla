# 06 · GitHub Actions 自動部署

## 運作方式

```
推送程式碼到 main
      │
      ▼
GitHub Actions（.github/workflows/deploy.yml）
      │  用專用部署金鑰 SSH 到伺服器，只送出「deploy main <commit>」
      ▼
伺服器 infra/scripts/deploy.sh
      │  驗證指令 → git 取得該版本 → docker compose up --build --wait → 清理舊映像檔
      ▼
GitHub 的 Actions 頁面顯示 ✅ / ❌ 與完整記錄
```

### 安全設計

- 部署金鑰在伺服器的 `authorized_keys` 裡被 `command=` 鎖定，**只能執行 deploy.sh**。不能開 shell、不能轉發 port。金鑰就算外洩，也只能觸發部署已經在 main 上的版本。
- `deploy.sh` 只接受 `deploy <分支> <40 碼 commit>` 格式的指令，而且該版本必須在 `origin/main` 上，其他指令一律拒絕。
- 伺服器的主機指紋預先寫在 `DEPLOY_KNOWN_HOSTS`，防止被假冒的伺服器騙走連線。
- 資料庫密碼等機密只存在伺服器的 `.env`（權限 600），不會進 git，也不會進 GitHub。
- 部署用 `starfly` 帳號執行，不是 root。

## 一次性設定（約 5 分鐘）

前提：已經執行過 `server-bootstrap.sh`。

### 1. 在伺服器上執行設定腳本（root）

```bash
curl -fsSL https://raw.githubusercontent.com/starflytesla-cpu/starflytesla/claude/exciting-fermi-nad1gj/infra/scripts/setup-deploy.sh -o setup-deploy.sh
bash setup-deploy.sh
```

腳本最後會印出 3 段內容：`DEPLOY_HOST`、`DEPLOY_KNOWN_HOSTS`、`DEPLOY_SSH_KEY`。

### 2. 貼到 GitHub Secrets

1. 打開 https://github.com/starflytesla-cpu/starflytesla/settings/secrets/actions
2. 按 **New repository secret**
3. **Name** 填 `DEPLOY_HOST`，**Secret** 貼上對應內容，按 **Add secret**
4. 用同樣方式新增 `DEPLOY_KNOWN_HOSTS` 和 `DEPLOY_SSH_KEY`

`DEPLOY_SSH_KEY` 要整段複製，從 `-----BEGIN OPENSSH PRIVATE KEY-----` 到 `-----END OPENSSH PRIVATE KEY-----`，兩行都要包含。

貼完後在伺服器上執行 `clear`，清掉畫面上的私鑰。

### 3. 建立 main 分支

自動部署只在 main 分支更新時觸發。main 分支建立後，第一次部署會自動執行。

## 日常使用

- **自動部署**：程式碼合併到 main 就會自動部署。
- **手動重新部署**：GitHub → Actions → Deploy → Run workflow。
- **查看結果**：GitHub → Actions，點進任一次執行可以看到完整記錄。
- **在伺服器上手動部署**：`bash /data/starfly/app/infra/scripts/deploy.sh`
- **部署歷史**：`cat /data/starfly/deploy-history.log`
- **編輯 API Key 等設定**：`nano /data/starfly/.env`，改完後重新部署一次。

## 更換部署金鑰

在伺服器上重跑 `bash setup-deploy.sh`：舊金鑰立即失效，`.env` 不會被覆蓋。再把新的 `DEPLOY_SSH_KEY` 更新到 GitHub 即可。

> 路徑說明：資料碟有掛載到 `/data` 時用 `/data/starfly`，否則用 `/srv/starfly`。
