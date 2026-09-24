#!/usr/bin/env bash
# VPS 壓測：檢查規格、CPU 是否被超賣（steal）、磁碟寫入速度，並模擬渲染 30 秒 1080x1920 成片。
# 用法：bash vps-bench.sh        （需要 ffmpeg；Ubuntu 可用 apt-get install -y ffmpeg 安裝）
set -euo pipefail

command -v ffmpeg >/dev/null || { echo "請先安裝 ffmpeg：sudo apt-get install -y ffmpeg"; exit 1; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "== 規格 =="
echo "CPU 核心數 : $(nproc)"
echo "CPU 型號   : $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)"
echo "記憶體     : $(free -h | awk '/Mem:/{print $2}')"
df -h / | awk 'NR==2{print "系統碟     : 共 "$2"，可用 "$4}'

echo
echo "== CPU steal（被其他租戶搶走的 CPU 比例，持續 >5% 代表超賣嚴重）=="
# 在滿載時取樣才有意義，所以邊壓 CPU 邊量
( for _ in $(seq "$(nproc)"); do timeout 10 sh -c 'while :; do :; done' & done; wait ) &
sleep 2
vmstat 1 6 | awk 'NR>3{s+=$17; n++} END{printf "滿載時平均 steal：%.1f%%\n", s/n}'
wait

echo
echo "== 磁碟寫入速度 =="
dd if=/dev/zero of="$WORK/dd.bin" bs=1M count=1024 oflag=direct 2>&1 | tail -1
rm -f "$WORK/dd.bin"

# 模擬典型混剪：橫式素材 → 直式 1080x1920（模糊背景 + 前景置中）+ 配樂
render() {
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "testsrc2=size=1920x1080:rate=30:duration=30" \
    -f lavfi -i "sine=frequency=440:duration=30" \
    -filter_complex "[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20[bg];[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]" \
    -map "[v]" -map 1:a -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k \
    "$WORK/out_$1.mp4"
}

echo
echo "== 渲染測試：30 秒 1080x1920 成片 =="
for i in 1 2 3; do
  s=$(date +%s.%N); render "$i"; e=$(date +%s.%N)
  awk -v i="$i" -v s="$s" -v e="$e" 'BEGIN{printf "第 %d 支：%.1f 秒\n", i, e-s}'
done

echo
echo "== 併發測試：同時渲染 2 支 =="
s=$(date +%s.%N); render p1 & render p2 & wait; e=$(date +%s.%N)
awk -v s="$s" -v e="$e" 'BEGIN{t=e-s; printf "2 支共 %.1f 秒 → 推估每小時可產出約 %.0f 支\n", t, 3600/t*2}'

echo
echo "參考：單支 < 60 秒、steal < 5% 就足夠應付一個帳號群（每天約 15 支）。"
