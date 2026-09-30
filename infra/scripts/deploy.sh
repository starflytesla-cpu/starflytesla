#!/usr/bin/env bash
# 在伺服器上部署 / 更新：拉取最新程式碼 → 重建並啟動所有服務 → 等待健康檢查通過。
#   bash infra/scripts/deploy.sh
#
# 第一次執行時，會從 .env.example 建立 .env，並把所有 change-me 換成隨機密碼，
# 最後印出管理員的登入帳密（只顯示這一次，也可以在 .env 裡查到）。
# 整個流程包在 main() 裡：bash 會先讀完整個函式才執行，
# 所以 git pull 更新本檔案時，不會影響正在執行的這一次部署。
set -euo pipefail

# 把 .env 裡值為空或 change-me 開頭的變數換成隨機值；回傳 0 代表有換。
randomize_placeholder() {
  local name=$1 current
  current=$(grep -E "^${name}=" .env | head -1 | cut -d= -f2- || true)
  if [[ -n $current && $current != change-me* ]]; then
    return 1
  fi
  local value
  value=$(openssl rand -hex 24)
  if grep -qE "^${name}=" .env; then
    sed -i "s|^${name}=.*|${name}=${value}|" .env
  else
    printf '%s=%s\n' "$name" "$value" >> .env
  fi
}

# 把 .env.example 有、但 .env 缺少的變數補上（舊版建立的 .env 或新增設定時）。
add_missing_vars() {
  local line name
  while IFS= read -r line; do
    [[ $line =~ ^([A-Z_][A-Z0-9_]*)= ]] || continue
    name=${BASH_REMATCH[1]}
    if ! grep -qE "^${name}=" .env; then
      printf '%s\n' "$line" >> .env
      echo "    補上缺少的設定 $name"
    fi
  done < .env.example
}

env_value() {
  grep -E "^$1=" .env | head -1 | cut -d= -f2- || true
}

main() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.."

  echo "==> 取得最新程式碼"
  git pull --ff-only --quiet
  echo "    版本：$(git log -1 --format='%h %s')"

  if [[ ! -f .env ]]; then
    cp .env.example .env
    chmod 600 .env
    echo "==> 已建立 .env"
  fi
  add_missing_vars
  local new_admin=""
  for name in POSTGRES_PASSWORD SECRET_KEY ADMIN_PASSWORD; do
    if randomize_placeholder "$name"; then
      echo "    已產生隨機的 $name"
      if [[ $name == ADMIN_PASSWORD ]]; then new_admin=yes; fi
    fi
  done

  echo "==> 建置並啟動服務（第一次約需 3～5 分鐘）"
  docker compose -f infra/docker-compose.yml --env-file .env \
    up -d --build --remove-orphans --wait --wait-timeout 600
  docker compose -f infra/docker-compose.yml --env-file .env ps

  echo "==> 清理舊映像檔"
  docker image prune -f >/dev/null

  printf '%s %s\n' "$(date -u +%FT%TZ)" "$(git rev-parse HEAD)" >> .deploy-history.log

  local site
  site=$(env_value SITE_ADDRESS)
  if [[ -z $site || $site == :* ]]; then
    site="http://$(hostname -I | awk '{print $1}')"
  else
    site="https://${site}"
  fi
  echo
  echo "==> 部署完成：$site"
  if [[ -n $new_admin ]]; then
    echo
    echo "    第一次部署，管理員登入資訊（請立即登入並在右上角「修改密碼」）："
    echo "      帳號：$(env_value ADMIN_EMAIL)"
    # 由 GitHub Actions 執行時記錄是公開的，不能印出密碼
    if [[ -n ${DEPLOY_HIDE_SECRETS:-} ]]; then
      echo "      密碼：請在伺服器執行 grep ADMIN_PASSWORD .env 查看"
    else
      echo "      密碼：$(env_value ADMIN_PASSWORD)"
    fi
  fi
}

main "$@"; exit
