#!/usr/bin/env bash
# 伺服器維運指令。GitHub Actions（.github/workflows/ops.yml）用一把受限 SSH 金鑰呼叫本腳本，
# 那把金鑰在 authorized_keys 裡被鎖定成只能執行這裡，指令放在 SSH_ORIGINAL_COMMAND。
# 也可以在伺服器上手動執行：bash infra/scripts/ops.sh status
#
# 允許的指令（其他一律拒絕）：
#   status                 版本、容器狀態、健康檢查、磁碟與記憶體
#   smoke                  透過網站入口與直連 API 測試健康檢查與管理員登入（只顯示狀態碼與耗時）
#   logs <服務> [行數]      服務：api / web / postgres；行數最多 500；IP 與 Email 會遮罩
#   deploy                 執行 deploy.sh，完成後自動跑 smoke
#   restart <服務>          重啟 api / web
#
# 倉庫是公開的，Actions 記錄任何人都看得到：絕對不要在這裡輸出 .env 或任何密碼。
# 整個流程包在 main() 裡，deploy 期間 git pull 更新本檔案時不影響這一次執行。
set -euo pipefail

COMPOSE=(docker compose -f infra/docker-compose.yml --env-file .env)

redact() {
  sed -E \
    -e 's/([0-9]{1,3}\.[0-9]{1,3})\.[0-9]{1,3}\.[0-9]{1,3}/\1.x.x/g' \
    -e 's/[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})/***@\1/g'
}

env_value() {
  grep -E "^$1=" .env | head -1 | cut -d= -f2- || true
}

# 印出 HTTP 狀態碼與耗時；逾時或連線失敗時狀態碼為 000
probe() {
  local label=$1
  shift
  local result
  result=$(curl -s -o /dev/null -m 20 -w '%{http_code} %{time_total}s' "$@" || true)
  printf '  %-28s %s\n' "$label" "${result:-000 失敗}"
}

cmd_status() {
  echo "== 版本"
  git log -1 --format='  %h %ci %s'
  echo "== 容器"
  "${COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'
  echo "== 健康檢查"
  probe "網站入口 /" http://localhost/
  probe "網站入口 /api/health" http://localhost/api/health
  echo "== 資源"
  uptime
  free -h
  df -h / /data 2>/dev/null || df -h /
  echo "== 最近部署"
  tail -5 .deploy-history.log 2>/dev/null || echo "  （沒有記錄）"
}

cmd_smoke() {
  local body
  body=$(printf '{"email":"%s","password":"%s"}' "$(env_value ADMIN_EMAIL)" "$(env_value ADMIN_PASSWORD)")
  echo "== 透過網站入口（Caddy → API）"
  probe "GET /api/health" http://localhost/api/health
  probe "GET /api/auth/me（應為 401）" http://localhost/api/auth/me
  probe "POST /api/auth/login" -H 'content-type: application/json' -d "$body" http://localhost/api/auth/login
  echo "== 直連 API 容器（略過 Caddy）"
  "${COMPOSE[@]}" exec -T api python - <<'PY' || echo "  直連 API 失敗"
import json, os, time, urllib.error, urllib.request

def call(label, path, body=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:8000{path}",
        data=json.dumps(body).encode() if body else None,
        headers={"content-type": "application/json"},
    )
    start = time.monotonic()
    try:
        status = urllib.request.urlopen(req, timeout=20).status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except Exception as exc:  # 逾時或連線失敗
        status = type(exc).__name__
    print(f"  {label:<28} {status} {time.monotonic() - start:.3f}s")

call("GET /api/health", "/api/health")
call("POST /api/auth/login", "/api/auth/login",
     {"email": os.environ.get("ADMIN_EMAIL", ""), "password": os.environ.get("ADMIN_PASSWORD", "")})
PY
  echo "  （登入 401 代表管理員已在網頁上改過密碼，屬正常）"
}

cmd_logs() {
  local service=${1:-} lines=${2:-100}
  [[ $service =~ ^(api|web|postgres)$ ]] || { echo "服務只能是 api / web / postgres" >&2; exit 2; }
  [[ $lines =~ ^[0-9]+$ ]] && (( lines >= 1 && lines <= 500 )) || { echo "行數需為 1～500" >&2; exit 2; }
  "${COMPOSE[@]}" logs --no-color --tail "$lines" "$service" 2>&1 | redact
}

cmd_restart() {
  local service=${1:-}
  [[ $service =~ ^(api|web)$ ]] || { echo "只能重啟 api / web" >&2; exit 2; }
  "${COMPOSE[@]}" restart "$service"
  "${COMPOSE[@]}" ps "$service"
}

main() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.."
  local request=${SSH_ORIGINAL_COMMAND:-${*:-status}}
  local -a args
  read -r -a args <<< "$request"
  echo "### ops: ${args[*]} @ $(date -u +%FT%TZ)"
  case "${args[0]:-}" in
    status) cmd_status ;;
    smoke) cmd_smoke ;;
    logs) cmd_logs "${args[1]:-}" "${args[2]:-100}" ;;
    deploy)
      DEPLOY_HIDE_SECRETS=1 bash infra/scripts/deploy.sh 2>&1 | redact
      cmd_smoke
      ;;
    restart) cmd_restart "${args[1]:-}" ;;
    *)
      echo "不支援的指令：${args[0]:-（空白）}" >&2
      exit 2
      ;;
  esac
}

main "$@"; exit
