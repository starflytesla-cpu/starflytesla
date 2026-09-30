#!/usr/bin/env bash
# 設定 GitHub Actions 自動部署。先執行過 server-bootstrap.sh，再用 root 執行一次：
#   bash setup-deploy.sh            （預設部署 main 分支）
#
# 會做的事：
#   1. 把專案 clone 到 <資料目錄>/starfly/app
#   2. 建立 <資料目錄>/starfly/.env，自動產生資料庫與 MinIO 的隨機密碼（只存在伺服器上）
#   3. 產生一把專用部署金鑰，在 authorized_keys 裡鎖定成「只能執行 deploy.sh」
#   4. 印出要貼到 GitHub Secrets 的 3 個值
#
# 重跑會換一把新的部署金鑰（舊的立即失效），.env 不會被覆蓋。
set -euo pipefail

REPO_URL=https://github.com/starflytesla-cpu/starflytesla.git
DEPLOY_USER=starfly
BRANCH=${1:-main}
KEY_COMMENT=github-actions-deploy

[[ $EUID -eq 0 ]] || { echo "請用 root 執行"; exit 1; }
id "$DEPLOY_USER" >/dev/null 2>&1 || { echo "找不到 $DEPLOY_USER 帳號，請先執行 server-bootstrap.sh"; exit 1; }
command -v docker >/dev/null || { echo "找不到 docker，請先執行 server-bootstrap.sh"; exit 1; }

if mountpoint -q /data; then BASE=/data/starfly; else BASE=/srv/starfly; fi
APP=$BASE/app
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$BASE"

echo "==> 1/4 取得程式碼到 $APP"
if [[ -d $APP/.git ]]; then
  echo "已存在，跳過"
else
  sudo -u "$DEPLOY_USER" git clone --quiet "$REPO_URL" "$APP"
fi

echo "==> 2/4 建立 $BASE/.env"
if [[ -f $BASE/.env ]]; then
  echo "已存在，不覆蓋"
else
  gen() { openssl rand -hex 24; }
  sed -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(gen)/" \
      -e "s/^MINIO_ROOT_PASSWORD=.*/MINIO_ROOT_PASSWORD=$(gen)/" \
      "$APP/.env.example" > "$BASE/.env"
  chown "$DEPLOY_USER:$DEPLOY_USER" "$BASE/.env"
  chmod 600 "$BASE/.env"
  echo "已產生隨機密碼（之後要填 API Key 時編輯這個檔案）"
fi

echo "==> 3/4 產生部署金鑰"
KEYDIR=$(mktemp -d)
trap 'rm -rf "$KEYDIR"' EXIT
ssh-keygen -q -t ed25519 -N "" -C "$KEY_COMMENT" -f "$KEYDIR/key"
SSH_DIR=/home/$DEPLOY_USER/.ssh
AUTH=$SSH_DIR/authorized_keys
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$SSH_DIR"
touch "$AUTH"
sed -i "/ $KEY_COMMENT\$/d" "$AUTH"   # 移除舊的部署金鑰
echo "command=\"DEPLOY_BRANCH=$BRANCH $APP/infra/scripts/deploy.sh\",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty $(cat "$KEYDIR/key.pub")" >> "$AUTH"
chown "$DEPLOY_USER:$DEPLOY_USER" "$AUTH"
chmod 600 "$AUTH"

HOST=$(ip -4 route get 1.1.1.1 | awk '{for (i=1;i<=NF;i++) if ($i=="src") print $(i+1)}')

echo "==> 4/4 請到 GitHub 設定以下 3 個 Secrets"
echo "    位置：倉庫頁面 → Settings → Secrets and variables → Actions → New repository secret"
echo
echo "────────── Name: DEPLOY_HOST ──────────"
echo "$HOST"
echo
echo "────────── Name: DEPLOY_KNOWN_HOSTS ──────────"
echo "$HOST $(cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub)"
echo
echo "────────── Name: DEPLOY_SSH_KEY（包含 BEGIN 和 END 兩行，整段複製）──────────"
cat "$KEYDIR/key"
echo "──────────────────────────────────────────────"
echo
echo "這把私鑰只顯示這一次，伺服器上不會保留。貼到 GitHub 後可以執行 clear 清掉畫面。"
echo "部署分支：$BRANCH"
