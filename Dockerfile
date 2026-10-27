FROM python:3.11-slim

WORKDIR /app

# Cài font chữ để vẽ ảnh QR chuẩn đẹp trên Linux Cloud VPS
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cấp quyền ghi đầy đủ cho SQLite (shop.db-wal) và log trên Cloud Container (HuggingFace uid=1000)
RUN chmod -R 777 /app

# Mở cổng 7860 (HuggingFace Spaces) và 8080 (Render / Railway / Fly.io)
ENV PORT=7860
ENV PYTHONIOENCODING=utf-8
EXPOSE 7860 8080

CMD ["python", "watchdog.py"]
