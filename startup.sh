#!/bin/bash
set -e

echo "=== Job Search API startup ==="
echo "Python: $(python --version)"
echo "PORT: ${PORT:-8000}"

# Применить схему БД если DATABASE_URL задан
if [ -n "$DATABASE_URL" ]; then
    echo "Инициализация схемы БД..."
    python init_db.py && echo "✅ БД готова" || echo "⚠️ init_db.py завершился с ошибкой (продолжаем)"
fi

echo "Запускаем uvicorn..."
exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1 \
    --log-level info
