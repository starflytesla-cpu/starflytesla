#!/usr/bin/env bash
# 開啟 SSH 金鑰登入（保留密碼登入不變）。有些主機商模板預設只允許密碼登入，
# 導致 GitHub Actions 維運通道與 ssh-copy-id 都無法使用。用 root 執行：
#   bash infra/scripts/enable-ssh-key.sh
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "請用 root 執行"; exit 1; }

# sshd 對同一設定取第一個出現的值；Ubuntu 的 sshd_config 開頭就 Include 這個目錄，
# 用 00- 開頭可以蓋過模板在其他檔案裡的設定。
cat > /etc/ssh/sshd_config.d/00-starfly-pubkey.conf <<CONF
PubkeyAuthentication yes
AuthenticationMethods any
CONF

mkdir -p /run/sshd
sshd -t
systemctl reload ssh 2>/dev/null || systemctl restart ssh

effective=$(sshd -T 2>/dev/null | grep -E '^(pubkeyauthentication|authenticationmethods|passwordauthentication) ')
echo "$effective" | sed 's/^/  /'
if grep -qx 'pubkeyauthentication yes' <<< "$effective"; then
  echo "完成：金鑰登入已開啟，密碼登入維持不變。"
else
  echo "金鑰登入仍未開啟，請把上面的輸出截圖給 Claude。" >&2
  exit 1
fi
