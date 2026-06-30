# ── Dockerfile для Job Search API ─────────────────────────────────────────
FROM python:3.11-slim

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Непривилегированный пользователь
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Зависимости — отдельным слоем для кэширования
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY . .

# Права на скрипт запуска и логи
RUN chmod +x startup.sh && \
    chown -R appuser:appgroup /app

# Переключаемся на непривилегированного пользователя
USER appuser

# Порт (Railway/Render подставляет $PORT)
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["./startup.sh"]
