# 05 · 伺服器初始化與部署

目前的伺服器：QQG.NET 洛杉磯 `6C12G-32T-BGP`，Ubuntu 24.04，IP `50.114.172.174`，年付 US$70（2026-09-29 開通）。

> 倉庫是**公開**的。伺服器密碼、API Key 等任何機密都不能提交進 git。

## 分工

- **Claude（雲端開發環境）**：寫程式、寫腳本、測試，推送到 GitHub。
- **伺服器**：只需要執行專案裡寫好的腳本。每個步驟都是一行指令。

## 第一次設定

在自己電腦的終端機登入伺服器：

```bash
ssh -o PubkeyAuthentication=no root@50.114.172.174
```

登入後一行一行執行：

```bash
git clone https://github.com/starflytesla-cpu/starflytesla.git && cd starflytesla
```

```bash
bash infra/scripts/server-bootstrap.sh
```

腳本問是否格式化資料碟時，先確認它顯示的是約 150G 的磁碟，再輸入 `yes`。

```bash
bash infra/bench/vps-bench.sh
```

把初始化腳本最後的「完成」摘要和壓測結果截圖給 Claude。

### 初始化腳本做了什麼

`infra/scripts/server-bootstrap.sh`（root 執行，可重複執行）：

1. 系統更新，安裝基本工具
2. 掛載 150 GB 資料碟到 `/data`。只有在找到完全空白的磁碟、而且確認同意時才會格式化
3. 建立 4 GB swap
4. 安裝 Docker，資料放在 `/data/docker`
5. 建立部署帳號 `starfly`
6. 防火牆只開放 SSH、80、443；啟用 fail2ban 和自動安全更新
7. 只有在指定 `DISABLE_SSH_PASSWORD=yes` 時，才會關閉 SSH 密碼登入（務必先確認金鑰登入可用）

## 之後每次更新

Claude 推送新版本後，登入伺服器執行：

```bash
cd starflytesla && bash infra/scripts/deploy.sh
```

腳本會拉取最新程式碼、重建並啟動所有服務，並等待健康檢查通過。第一次執行時會自動建立 `.env` 並產生隨機密碼。有錯誤時，把畫面截圖給 Claude。

## 網域（Phase 0 部署前準備好即可）

1. 買一個網域（例如在 Cloudflare、Namecheap 購買）。
2. 新增一筆 DNS **A 記錄**，例如 `app.你的網域.com` 指向 `50.114.172.174`。
3. 部署時，Caddy 會自動申請並續期 HTTPS 憑證。
