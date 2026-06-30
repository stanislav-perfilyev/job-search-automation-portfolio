# ══════════════════════════════════════════════════════════════════
# Job Search API — Makefile
# ══════════════════════════════════════════════════════════════════

COMPOSE      = docker compose
COMPOSE_PROD = docker compose -f docker-compose.yml -f docker-compose.prod.yml
APP_SERVICE  = api
DB_SERVICE   = postgres

.PHONY: help dev prod stop logs shell db build clean ps

# По умолчанию — показать помощь
help:
	@echo ""
	@echo "  make dev     — запустить dev окружение (hot reload)"
	@echo "  make prod    — запустить production (nginx + no reload)"
	@echo "  make stop    — остановить все контейнеры"
	@echo "  make logs    — логи всех сервисов (Ctrl+C для выхода)"
	@echo "  make shell   — войти в контейнер app (bash)"
	@echo "  make db      — подключиться к PostgreSQL (psql)"
	@echo "  make build   — пересобрать образы"
	@echo "  make clean   — удалить контейнеры + тома (ОСТОРОЖНО: данные БД)"
	@echo "  make ps      — статус контейнеров"
	@echo ""

## ── Dev ──────────────────────────────────────────────────────────
dev:
	$(COMPOSE) up -d
	@echo ""
	@echo "  API:    http://localhost:8000"
	@echo "  Docs:   http://localhost:8000/docs"
	@echo "  Health: http://localhost:8000/health"
	@echo ""

## ── Production ───────────────────────────────────────────────────
prod:
	$(COMPOSE_PROD) up -d
	@echo ""
	@echo "  API via Nginx: http://localhost"
	@echo ""

## ── Управление ───────────────────────────────────────────────────
stop:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

logs-api:
	$(COMPOSE) logs -f $(APP_SERVICE)

shell:
	$(COMPOSE) exec $(APP_SERVICE) bash

db:
	$(COMPOSE) exec $(DB_SERVICE) psql -U jobuser -d jobsearch

build:
	$(COMPOSE) build --no-cache

clean:
	@echo "ВНИМАНИЕ: удаляет все данные PostgreSQL!"
	@read -p "Продолжить? [y/N] " confirm && [ "$$confirm" = "y" ]
	$(COMPOSE) down -v --remove-orphans

ps:
	$(COMPOSE) ps
