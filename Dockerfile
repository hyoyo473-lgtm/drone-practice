FROM python:3.12-slim
WORKDIR /app
# 時區資料：讓「登錄時間」顯示台灣時間
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
COPY server.py .
COPY static ./static
ENV PORT=8080 DATA_DIR=/data TZ=Asia/Taipei
VOLUME ["/data"]
EXPOSE 8080
CMD ["python", "-u", "server.py"]
