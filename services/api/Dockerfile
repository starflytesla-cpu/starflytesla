FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# 素材分析與成片渲染需要 FFmpeg；字幕字型：Noto（拉丁 / 阿拉伯 / 泰文）與 Noto CJK（中日韓）
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-noto-core fonts-noto-cjk \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

# /media 掛載素材 volume；第一次建立 volume 時會沿用這裡的擁有者
RUN useradd --system --uid 10001 starfly && install -d -o starfly -g starfly /media
USER starfly

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# 啟動前先套用資料庫遷移；只接受來自 Compose 網路內 web（Caddy）的轉發標頭。
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
