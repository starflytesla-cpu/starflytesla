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

## 部署與更新

Claude 推送新版本後，登入伺服器執行：

```bash
cd starflytesla && bash infra/scripts/deploy.sh
```

腳本會拉取最新程式碼、建置並啟動所有服務，並等待健康檢查通過。

**第一次部署**（約 3～5 分鐘）時，腳本會：

1. 從 `.env.example` 建立 `.env`，自動產生資料庫密碼、`SECRET_KEY` 與管理員密碼。
2. 最後印出網址與**管理員帳號密碼**（只顯示這一次；忘記的話可以執行 `grep ADMIN_ .env` 查看）。

接著：

1. 用瀏覽器打開印出的網址（例如 `http://50.114.172.174`），用管理員帳密登入。
2. 右上角 →「修改密碼」，換成自己的密碼。
3. 左側「系統設定 → 模型渠道」→「新增渠道」，選 DeepSeek 並貼上 API Key，按模型旁的「測試」。
4. 再新增「豆包（BytePlus ModelArk）」渠道並測試。
5. 到「用量與成本」確認有看到兩筆成本記錄。

有錯誤時，把畫面截圖給 Claude。查看後端日誌：

```bash
docker compose -f infra/docker-compose.yml logs --tail 100 api
```

## 網域與 HTTPS

1. 買一個網域（例如在 Cloudflare、Namecheap 購買）。
2. 新增一筆 DNS **A 記錄**，例如 `app.你的網域.com` 指向 `50.114.172.174`。若使用 Cloudflare，先把代理（橘色雲朵）關掉，讓 Caddy 能直接申請憑證。
3. 在伺服器的專案目錄編輯 `.env`，把 `SITE_ADDRESS=:80` 改成 `SITE_ADDRESS=app.你的網域.com`：

   ```bash
   nano .env
   ```

4. 重新部署：`bash infra/scripts/deploy.sh`。Caddy 會自動申請並續期 HTTPS 憑證，之後改用 `https://app.你的網域.com` 開啟。
