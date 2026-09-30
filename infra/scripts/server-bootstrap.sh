#!/usr/bin/env bash
# 新 VPS 初始化（Ubuntu 22.04 / 24.04），用 root 執行一次：
#   bash server-bootstrap.sh
#
# 非互動執行時（例如由 Claude Code 代為執行）可用環境變數確認危險步驟：
#   FORMAT_DATA_DISK=yes      同意格式化偵測到的空白資料碟
#   DISABLE_SSH_PASSWORD=yes  關閉 SSH 密碼登入（務必先確認金鑰登入可用）
#
# 會做的事：
#   1. 系統更新、安裝基本工具（含 ffmpeg，供壓測使用）
#   2. 掛載資料碟到 /data（只有在找到「完全空白」的磁碟且你輸入 yes 時才會格式化）
#   3. 建立 4 GB swap（如果還沒有）
#   4. 安裝 Docker，並把 Docker 資料放到 /data/docker
#   5. 建立部署用帳號 starfly（有 sudo 與 docker 權限），複製 root 的 SSH 公鑰
#   6. 防火牆只開 SSH / 80 / 443，並啟用 fail2ban 與自動安全更新
#   7. 指定 DISABLE_SSH_PASSWORD=yes 時，關閉 SSH 密碼登入
#
# 可以重複執行，已完成的步驟會跳過。
set -euo pipefail

DEPLOY_USER=starfly
DATA_MOUNT=/data

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[注意] %s\033[0m\n' "$*"; }

[[ $EUID -eq 0 ]] || { echo "請用 root 執行"; exit 1; }
. /etc/os-release
[[ $ID == ubuntu ]] || { echo "只支援 Ubuntu，目前是 $PRETTY_NAME"; exit 1; }

# ---------------------------------------------------------------- 1. 系統更新
log "1/7 系統更新與基本工具"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold
apt-get install -y -q ca-certificates curl git ufw fail2ban unattended-upgrades htop ffmpeg

# ---------------------------------------------------------------- 2. 資料碟
log "2/7 資料碟"
if mountpoint -q "$DATA_MOUNT"; then
  echo "$DATA_MOUNT 已掛載，跳過"
else
  lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
  # 找「實體磁碟、>= 10GB、沒有分割區 / 分割表、沒有檔案系統、沒有掛載、不是 swap」的候選
  CANDIDATE=""
  for dev in $(lsblk -dnpo NAME,TYPE | awk '$2=="disk"{print $1}'); do
    [[ $dev =~ ^/dev/(vd|sd|xvd|nvme) ]] || continue                        # 排除 zram、ram 等虛擬裝置
    (( $(lsblk -dnbo SIZE "$dev") >= 10*1024*1024*1024 )) || continue       # 太小
    [[ $(lsblk -no NAME "$dev" | wc -l) -eq 1 ]] || continue                 # 有分割區
    [[ -z $(lsblk -no MOUNTPOINTS "$dev" | tr -d '[:space:]') ]] || continue # 已掛載
    swapon --show=NAME --noheadings | grep -qx "$dev" && continue             # 是 swap
    [[ -z $(blkid -p -o value -s TYPE "$dev" 2>/dev/null) ]] || continue     # 已有檔案系統
    [[ -z $(blkid -p -o value -s PTTYPE "$dev" 2>/dev/null) ]] || continue   # 已有分割表
    CANDIDATE=$dev; break
  done
  if [[ -z $CANDIDATE ]]; then
    warn "找不到空白資料碟（可能已被分割或已格式化）。請把上面 lsblk 的輸出貼給開發者，這一步先跳過。"
  else
    echo
    warn "找到空白磁碟 $CANDIDATE（$(lsblk -dno SIZE "$CANDIDATE")），將格式化為 ext4 並掛載到 $DATA_MOUNT。"
    ans=${FORMAT_DATA_DISK:-}
    if [[ -z $ans && -t 0 ]]; then
      read -r -p "確認格式化 $CANDIDATE？輸入 yes 繼續，其他任意鍵跳過：" ans || ans=""
    fi
    if [[ $ans == yes ]]; then
      mkfs.ext4 -q -L data "$CANDIDATE"
      mkdir -p "$DATA_MOUNT"
      echo "UUID=$(blkid -o value -s UUID "$CANDIDATE") $DATA_MOUNT ext4 defaults,noatime,nofail 0 2" >> /etc/fstab
      mount "$DATA_MOUNT"
      echo "已掛載：$(df -h "$DATA_MOUNT" | awk 'NR==2{print $2" 總容量"}')"
    else
      echo "略過資料碟（非互動執行時，加上 FORMAT_DATA_DISK=yes 才會格式化）"
    fi
  fi
fi
BASE_DIR=$DATA_MOUNT
mountpoint -q "$DATA_MOUNT" || BASE_DIR=/srv
mkdir -p "$BASE_DIR"

# ---------------------------------------------------------------- 3. swap
log "3/7 swap"
if swapon --show | grep -q .; then
  echo "已有 swap，跳過"
else
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap -q /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -q vm.swappiness=10
  echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf
  echo "已建立 4 GB swap"
fi

# ---------------------------------------------------------------- 4. Docker
log "4/7 Docker"
if ! command -v docker >/dev/null; then
  mkdir -p /etc/docker "$BASE_DIR/docker"
  cat > /etc/docker/daemon.json <<JSON
{
  "data-root": "$BASE_DIR/docker",
  "log-driver": "json-file",
  "log-opts": { "max-size": "20m", "max-file": "3" }
}
JSON
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
docker --version
docker compose version

# ---------------------------------------------------------------- 5. 部署帳號
log "5/7 部署帳號 $DEPLOY_USER"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG sudo,docker "$DEPLOY_USER"
echo "$DEPLOY_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-$DEPLOY_USER"
chmod 440 "/etc/sudoers.d/90-$DEPLOY_USER"
if [[ -s /root/.ssh/authorized_keys ]]; then
  install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
  AUTH_KEYS="/home/$DEPLOY_USER/.ssh/authorized_keys"
  # 合併而不是覆蓋，避免洗掉之後加入的部署金鑰
  MERGED=$(cat "$AUTH_KEYS" /root/.ssh/authorized_keys 2>/dev/null | awk 'NF && !seen[$0]++')
  printf '%s\n' "$MERGED" > "$AUTH_KEYS"
  chown "$DEPLOY_USER:$DEPLOY_USER" "$AUTH_KEYS"
  chmod 600 "$AUTH_KEYS"
  echo "已複製 SSH 公鑰給 $DEPLOY_USER"
fi
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$BASE_DIR/starfly"
echo "專案目錄：$BASE_DIR/starfly"

# ---------------------------------------------------------------- 6. 防火牆與防護
log "6/7 防火牆、fail2ban、自動安全更新"
mkdir -p /run/sshd
SSH_PORT=$(sshd -T 2>/dev/null | awk '/^port /{print $2; exit}' || true)
SSH_PORT=${SSH_PORT:-22}
ufw allow "$SSH_PORT/tcp" comment 'ssh'
ufw allow 80/tcp comment 'http'
ufw allow 443/tcp comment 'https'
ufw --force enable
ufw status verbose | head -20

cat > /etc/fail2ban/jail.d/sshd.local <<CONF
[sshd]
enabled = true
port = $SSH_PORT
maxretry = 5
bantime = 1h
CONF
systemctl enable fail2ban >/dev/null 2>&1 || true
systemctl restart fail2ban || warn "fail2ban 啟動失敗，請執行 journalctl -u fail2ban 查看原因（不影響其他步驟）"

cat > /etc/apt/apt.conf.d/20auto-upgrades <<CONF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF

# ---------------------------------------------------------------- 7. SSH
log "7/7 SSH 安全設定"
# 有些主機商模板預設關閉金鑰登入（只剩密碼），先確保金鑰登入開啟。
# 放在 00- 開頭的檔案，sshd 取第一個出現的設定值，才能蓋過模板的設定。
cat > /etc/ssh/sshd_config.d/00-starfly-pubkey.conf <<CONF
PubkeyAuthentication yes
AuthenticationMethods any
CONF
if [[ ${DISABLE_SSH_PASSWORD:-} == yes && -s /root/.ssh/authorized_keys ]]; then
  cat > /etc/ssh/sshd_config.d/10-starfly.conf <<CONF
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
CONF
  echo "已關閉密碼登入，之後只能用 SSH 金鑰登入（root 或 $DEPLOY_USER）"
else
  warn "保留 SSH 密碼登入。確認金鑰登入可用後，用 DISABLE_SSH_PASSWORD=yes 重跑本腳本即可關閉。"
fi
sshd -t
systemctl reload ssh 2>/dev/null || systemctl restart ssh

log "完成"
cat <<EOF
  CPU / 記憶體 : $(nproc) 核 / $(free -h | awk '/Mem:/{print $2}')
  磁碟         : $(df -h / | awk 'NR==2{print "系統碟可用 "$4}')$(mountpoint -q "$DATA_MOUNT" && df -h "$DATA_MOUNT" | awk 'NR==2{print "，資料碟可用 "$4}')
  Docker 資料  : $BASE_DIR/docker
  專案目錄     : $BASE_DIR/starfly
  防火牆       : 開放 $SSH_PORT / 80 / 443

下一步：在專案目錄執行壓測
  bash infra/bench/vps-bench.sh
EOF
