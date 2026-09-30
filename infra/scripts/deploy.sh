#!/usr/bin/env bash
# 在伺服器上部署 / 更新：拉取最新程式碼 → 重建並啟動所有服務 → 等待健康檢查通過。
#   bash infra/scripts/deploy.sh
#
# 第一次執行時，會從 .env.example 建立 .env，並自動產生資料庫與 MinIO 的隨機密碼。
# 整個流程包在 main() 裡：bash 會先讀完整個函式才執行，
# 所以 git pull 更新本檔案時，不會影響正在執行的這一次部署。
set -euo pipefail

main() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.."

  if [[ ! -f .env ]]; then
    echo "==> 建立 .env（產生隨機密碼）"
    gen() { openssl rand -hex 24; }
    sed -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(gen)/" \
        -e "s/^MINIO_ROOT_PASSWORD=.*/MINIO_ROOT_PASSWORD=$(gen)/" \
        .env.example > .env
    chmod 600 .env
  fi

  echo "==> 取得最新程式碼"
  git pull --ff-only --quiet
  echo "    版本：$(git log -1 --format='%h %s')"

  echo "==> 啟動服務"
  docker compose -f infra/docker-compose.yml --env-file .env \
    up -d --build --remove-orphans --wait --wait-timeout 300
  docker compose -f infra/docker-compose.yml --env-file .env ps

  echo "==> 清理舊映像檔"
  docker image prune -f >/dev/null

  printf '%s %s\n' "$(date -u +%FT%TZ)" "$(git rev-parse HEAD)" >> .deploy-history.log
  echo "==> 部署完成"
}

main "$@"; exit
