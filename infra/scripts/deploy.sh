#!/usr/bin/env bash
# 在伺服器上執行的部署腳本（由 GitHub Actions 透過受限 SSH 金鑰觸發，也可以手動執行）。
#
#   GitHub Actions：ssh starfly@HOST "deploy <branch> <commit-sha>"
#                   （部署金鑰在 authorized_keys 被鎖定成只能執行本腳本，指令放在 SSH_ORIGINAL_COMMAND）
#   手動：           bash deploy.sh             → 部署 DEPLOY_BRANCH 的最新版本
#
# 整個流程包在 main() 裡：bash 會先讀完整個函式再執行，
# 所以 git checkout 更新本檔案時，不會影響正在執行的這一次部署。
set -euo pipefail

main() {
  local app_dir base_dir env_file branch sha
  app_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
  base_dir=$(dirname "$app_dir")
  env_file="$base_dir/.env"
  branch=${DEPLOY_BRANCH:-main}

  # 要用 repo 擁有者（starfly）執行，避免 git 的 dubious ownership 錯誤與檔案權限混亂
  local owner
  owner=$(stat -c %U "$app_dir")
  if [[ $(id -un) != "$owner" ]]; then
    exec sudo -u "$owner" DEPLOY_BRANCH="$branch" SSH_ORIGINAL_COMMAND="${SSH_ORIGINAL_COMMAND:-}" bash "${BASH_SOURCE[0]}"
  fi

  # 解析指令：只接受 "deploy <branch> <40 碼 sha>"
  sha=""
  if [[ -n ${SSH_ORIGINAL_COMMAND:-} ]]; then
    if [[ $SSH_ORIGINAL_COMMAND =~ ^deploy\ ([A-Za-z0-9._/-]+)\ ([0-9a-f]{40})$ ]]; then
      if [[ ${BASH_REMATCH[1]} != "$branch" ]]; then
        echo "拒絕：只允許部署 $branch 分支（收到 ${BASH_REMATCH[1]}）" >&2
        exit 2
      fi
      sha=${BASH_REMATCH[2]}
    else
      echo "拒絕：不支援的指令" >&2
      exit 2
    fi
  fi

  [[ -f $env_file ]] || { echo "找不到 $env_file，請先執行 setup-deploy.sh" >&2; exit 1; }

  # 同一時間只允許一個部署
  exec 9>"$base_dir/.deploy.lock"
  flock -w 600 9 || { echo "等待其他部署逾時" >&2; exit 1; }

  cd "$app_dir"
  echo "==> 取得最新程式碼（$branch）"
  git fetch --prune --quiet origin
  [[ -n $sha ]] || sha=$(git rev-parse "origin/$branch")
  if ! git merge-base --is-ancestor "$sha" "origin/$branch"; then
    echo "拒絕：$sha 不在 origin/$branch 上" >&2
    exit 2
  fi
  git checkout --force --detach --quiet "$sha"
  echo "    版本：$(git log -1 --format='%h %s')"

  echo "==> 啟動服務"
  docker compose -f infra/docker-compose.yml --env-file "$env_file" \
    up -d --build --remove-orphans --wait --wait-timeout 300
  docker compose -f infra/docker-compose.yml --env-file "$env_file" ps

  echo "==> 清理舊映像檔"
  docker image prune -f >/dev/null

  printf '%s %s\n' "$(date -u +%FT%TZ)" "$sha" >> "$base_dir/deploy-history.log"
  echo "==> 部署完成：$sha"
}

main "$@"; exit
