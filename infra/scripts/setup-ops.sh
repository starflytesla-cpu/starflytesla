#!/usr/bin/env bash
# 一次性設定：讓 GitHub Actions 可以在這台伺服器執行維運指令（infra/scripts/ops.sh）。
# 在伺服器的專案目錄用 root 執行：bash infra/scripts/setup-ops.sh
#
# 會產生一把專用金鑰，加入 root 的 authorized_keys，並用 command= 鎖定成只能執行 ops.sh
# （不能開 shell、不能轉發 port）。最後印出要貼到 GitHub Secrets 的 3 個值。
# 重跑會換一把新金鑰，舊的立即失效。
set -euo pipefail

KEY_COMMENT=github-actions-ops

[[ $EUID -eq 0 ]] || { echo "請用 root 執行"; exit 1; }
APP=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
[[ -f $APP/infra/scripts/ops.sh ]] || { echo "找不到 ops.sh，請先 git pull"; exit 1; }
chmod +x "$APP/infra/scripts/ops.sh"

if sshd -T 2>/dev/null | grep -qx 'permitrootlogin no'; then
  echo "SSH 設定禁止 root 登入（PermitRootLogin no），GitHub Actions 將無法連線。" >&2
  exit 1
fi

KEYDIR=$(mktemp -d)
trap 'rm -rf "$KEYDIR"' EXIT
ssh-keygen -q -t ed25519 -N "" -C "$KEY_COMMENT" -f "$KEYDIR/key"

install -d -m 700 /root/.ssh
AUTH=/root/.ssh/authorized_keys
touch "$AUTH"
chmod 600 "$AUTH"
sed -i "/ ${KEY_COMMENT}\$/d" "$AUTH"
echo "command=\"$APP/infra/scripts/ops.sh\",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty $(cat "$KEYDIR/key.pub")" >> "$AUTH"

HOST=$(ip -4 route get 1.1.1.1 | awk '{for (i=1;i<=NF;i++) if ($i=="src") print $(i+1)}')

cat <<MSG

請到 GitHub 新增以下 3 個 Secret：
  https://github.com/starflytesla-cpu/starflytesla/settings/secrets/actions
  按「New repository secret」，Name 填左邊的名稱，Secret 貼上對應內容。

────────── Name: OPS_HOST ──────────
$HOST

────────── Name: OPS_KNOWN_HOSTS ──────────
$HOST $(cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub)

────────── Name: OPS_SSH_KEY（從 BEGIN 到 END 整段複製）──────────
$(cat "$KEYDIR/key")
──────────────────────────────────────

這把私鑰只顯示這一次，伺服器上不會保留。貼到 GitHub 後執行 clear 清掉畫面。
MSG
