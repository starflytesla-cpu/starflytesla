# 05 · 伺服器初始化步驟

目前的伺服器：QQG.NET 洛杉磯 `6C12G-32T-BGP`，Ubuntu 24.04，年付 US$70（2026-09-29 開通）。

> 倉庫是**公開**的。伺服器密碼、API Key 等任何機密都不能提交進 git（`.env` 已被 `.gitignore` 排除）。

## 步驟 1：設定 SSH 金鑰登入（建議，約 2 分鐘）

用金鑰登入比密碼安全。設定好之後，初始化腳本會自動關閉密碼登入，擋掉網路上大量的暴力破解嘗試。

**Mac / Linux**（在自己電腦的終端機執行）：

```bash
ssh-keygen -t ed25519            # 一路按 Enter 即可；已經有金鑰的話可以跳過
ssh-copy-id root@<伺服器IP>       # 輸入一次 root 密碼
```

**Windows**（PowerShell）：

```powershell
ssh-keygen -t ed25519
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@<伺服器IP> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

完成後執行 `ssh root@<伺服器IP>`，**不需要輸入密碼就能登入**，才算成功。

> 注意：之後換電腦時，需要把新電腦的公鑰也加進去；或是透過主機商後台的 VNC 控制台登入處理。

## 步驟 2：執行初始化腳本（約 5～10 分鐘）

登入伺服器後執行：

```bash
curl -fsSL https://raw.githubusercontent.com/starflytesla-cpu/starflytesla/claude/exciting-fermi-nad1gj/infra/scripts/server-bootstrap.sh -o bootstrap.sh
bash bootstrap.sh
```

腳本會做這些事（詳見 `infra/scripts/server-bootstrap.sh`）：

1. 系統更新，安裝基本工具
2. 掛載 150 GB 資料碟到 `/data`。**只有在找到完全空白的磁碟、而且你輸入 `yes` 時才會格式化**
3. 建立 4 GB swap
4. 安裝 Docker，資料放在 `/data/docker`
5. 建立部署帳號 `starfly`
6. 防火牆只開放 SSH、80、443；啟用 fail2ban（自動封鎖暴力破解的 IP）和自動安全更新
7. 如果步驟 1 已完成，關閉密碼登入

腳本可以重複執行，已經完成的步驟會自動跳過。

## 步驟 3：壓測

```bash
curl -fsSL https://raw.githubusercontent.com/starflytesla-cpu/starflytesla/claude/exciting-fermi-nad1gj/infra/bench/vps-bench.sh -o vps-bench.sh
bash vps-bench.sh
```

判斷標準：滿載時 steal < 5%，單支 30 秒成片渲染 < 60 秒。

## 步驟 4：網域（Phase 0 部署前準備好即可）

1. 買一個網域（例如在 Cloudflare、Namecheap、阿里雲國際站購買）。
2. 新增一筆 DNS **A 記錄**，例如 `app.你的網域.com` 指向伺服器 IP。
3. 部署時，Caddy 會自動申請並續期 HTTPS 憑證。

## 需要回報給開發者的內容

- 初始化腳本最後的「完成」摘要；如果中途出錯，貼上錯誤訊息
- 壓測腳本的完整輸出
- 網域名稱
