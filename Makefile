.PHONY: help dev up down logs shell db-shell migrate migrate-create seed test lint clean

help:
	@echo "Tchoucti / Dengoh — Commandes disponibles:"
	@echo ""
	@echo "  ── Développement ──────────────────────"
	@echo "  make dev            - Démarre l'env de développement (build + logs)"
	@echo "  make up             - Démarre en arrière-plan"
	@echo "  make down           - Arrête les conteneurs"
	@echo "  make logs           - Affiche les logs"
	@echo "  make shell          - Shell dans le backend"
	@echo "  make db-shell       - psql PostgreSQL"
	@echo ""
	@echo "  ── Base de données ────────────────────"
	@echo "  make migrate        - Applique les migrations Alembic"
	@echo "  make migrate-create - Crée une nouvelle migration"
	@echo "  make seed           - Seed la base"
	@echo ""
	@echo "  ── Qualité ────────────────────────────"
	@echo "  make test           - Lance les tests"
	@echo "  make lint           - Lint (ruff)"
	@echo "  make clean          - Supprime les volumes"

dev:
	docker compose up --build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

shell:
	docker compose exec backend bash

db-shell:
	docker compose exec postgres psql -U tchoucti_user -d tchoucti_db

migrate:
	docker compose exec backend alembic upgrade head

migrate-create:
	@read -p "Nom de la migration: " name; \
	docker compose exec backend alembic revision --autogenerate -m "$$name"

seed:
	docker compose exec backend python -m app.db.seed

test:
	docker compose exec backend pytest -v

lint:
	docker compose exec backend ruff check .

clean:
	docker compose down -v
	docker volume rm tchoucti_postgres_data tchoucti_redis_data tchoucti_minio_data 2>/dev/null || true
