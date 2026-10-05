#!/usr/bin/env bash
# 備份資料庫到伺服器資料碟（不會上傳到任何地方）。
#   bash infra/scripts/backup.sh            備份一次，保留最近 BACKUP_KEEP 份（預設 14）
#   bash infra/scripts/backup.sh --list     列出現有備份
#
# 備份檔是 pg_dump 自訂格式（.dump），內含帳號、密碼雜湊與加密後的 API Key：
# 只放在本機 BACKUP_DIR（權限 700 / 600），絕對不要放進 GitHub（倉庫是公開的）。
# 解密 API Key 需要同一台伺服器 .env 裡的 SECRET_KEY；還原步驟見 docs/05-server-setup.md。
# 素材檔（/media）不在備份範圍：檔案很大，且 git 與部署不會改動它們。
set -euo pipefail

COMPOSE=(docker compose -f infra/docker-compose.yml --env-file .env)

backup_dir() {
  if [[ -n ${BACKUP_DIR:-} ]]; then
    echo "$BACKUP_DIR"
  elif [[ -d /data ]]; then
    echo /data/backups/starfly
  else
    echo /var/backups/starfly
  fi
}

list_backups() {
  local dir
  dir=$(backup_dir)
  echo "== 資料庫備份（$dir）"
  if ! compgen -G "$dir/*.dump" >/dev/null; then
    echo "  （沒有備份）"
    return
  fi
  # 檔名格式：db-<UTC 時間>-<部署版本>.dump
  find "$dir" -maxdepth 1 -name '*.dump' -printf '  %f  %s bytes\n' | sort -r
  df -h "$dir" | tail -1 | awk '{print "  磁碟剩餘：" $4 "（" $5 " 已使用）"}'
}

run_backup() {
  local dir keep stamp version target tmp
  dir=$(backup_dir)
  keep=${BACKUP_KEEP:-14}
  install -d -m 700 "$dir"

  if [[ -z $("${COMPOSE[@]}" ps -q --status running postgres 2>/dev/null) ]]; then
    echo "  資料庫尚未啟動（第一次部署），略過備份"
    return 0
  fi

  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  # 記錄「備份當下伺服器正在跑的版本」，還原時才知道要搭配哪一版程式碼
  version=$({ tail -1 .deploy-history.log 2>/dev/null || true; } | awk '{print substr($2, 1, 7)}')
  target="$dir/db-${stamp}-${version:-unknown}.dump"
  tmp="$target.partial"

  umask 077
  if ! "${COMPOSE[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$tmp"; then
    rm -f "$tmp"
    echo "  [錯誤] 資料庫備份失敗" >&2
    return 1
  fi
  # 自訂格式的檔頭是 PGDMP；空檔或格式錯誤都視為失敗
  if [[ $(head -c 5 "$tmp") != PGDMP ]]; then
    rm -f "$tmp"
    echo "  [錯誤] 備份檔格式不正確" >&2
    return 1
  fi
  mv "$tmp" "$target"
  echo "  已備份：$(basename "$target")（$(stat -c %s "$target") bytes，sha256 $(sha256sum "$target" | cut -c1-12)）"

  # 只保留最近 keep 份
  find "$dir" -maxdepth 1 -name '*.dump' -printf '%f\n' | sort -r | tail -n +"$((keep + 1))" |
    while read -r old; do
      rm -f "$dir/$old"
      echo "  刪除舊備份：$old"
    done
}

main() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.."
  case "${1:-}" in
    --list) list_backups ;;
    "") run_backup ;;
    *)
      echo "用法：backup.sh [--list]" >&2
      exit 2
      ;;
  esac
}

main "$@"; exit
