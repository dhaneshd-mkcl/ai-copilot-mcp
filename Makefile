.PHONY: dev build test lint format clean docker-up docker-down help validate workspace
ifneq ("$(wildcard .env)","")
    include .env
    export
endif


## ── Development ──────────────────────────────────────────────────────────────

dev: validate workspace ## Start both backend and frontend in dev mode
	@echo "Starting AI Coding Copilot (backend + frontend)..."
	@bash start.sh

dev-backend: ## Start backend only
	@cd backend && python app.py

dev-frontend: ## Start frontend only
	@cd frontend && npm run dev

## ── Build ─────────────────────────────────────────────────────────────────────

build: ## Build frontend for production
	@cd frontend && npm run build

build-docker: ## Build Docker images
	@docker compose build

## ── Quality ───────────────────────────────────────────────────────────────────

lint: lint-py lint-js ## Run all linters

lint-py: ## Lint Python backend
	@echo "→ Linting Python..."
	@cd backend && python -m flake8 . --max-line-length=100 --exclude=__pycache__,.venv || true

lint-js: ## Lint Vue/JS frontend
	@echo "→ Linting JS/Vue..."
	@cd frontend && npx eslint src --ext .js,.vue || true

format: format-py format-js ## Format all code

format-py: ## Format Python with black
	@echo "→ Formatting Python..."
	@cd backend && python -m black . --line-length=100

format-js: ## Format JS/Vue with prettier
	@echo "→ Formatting JS/Vue..."
	@cd frontend && npx prettier --write "src/**/*.{js,vue,css}"

## ── Testing ───────────────────────────────────────────────────────────────────

test: test-py ## Run all tests

test-py: ## Run Python tests
	@echo "→ Running Python tests..."
	@cd backend && python -m pytest tests/ -v --tb=short 2>/dev/null || echo "No tests found."

## ── Docker ────────────────────────────────────────────────────────────────────

docker-up: ## Start services with Docker Compose
	@docker compose up -d

docker-down: ## Stop Docker Compose services
	@docker compose down

docker-logs: ## Follow Docker logs
	@docker compose logs -f

docker-restart: ## Restart Docker services
	@docker compose restart

reset-db: ## Reset both PostgreSQL and Redis databases
	@echo "→ Resetting databases..."
	@python backend/scripts/reset_db.py

## ── Utilities ─────────────────────────────────────────────────────────────────

install: ## Install all dependencies
	@echo "→ Installing Python dependencies..."
	@cd backend && pip install -r requirements.txt
	@echo "→ Installing Node dependencies..."
	@cd frontend && npm install

clean: ## Remove build artifacts and caches
	@find backend -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; true
	@find backend -name "*.pyc" -delete 2>/dev/null; true
	@rm -rf frontend/dist frontend/node_modules/.cache 2>/dev/null; true
	@echo "✓ Cleaned build artifacts"

workspace: ## Manage the workspace directory and permissions
	@echo "→ Managing workspace at $(ALLOWED_BASE_PATH)..."
	@mkdir -p $(ALLOWED_BASE_PATH)
	@if [ ! -w "$(ALLOWED_BASE_PATH)" ]; then \
		echo "❌ Error: Workspace $(ALLOWED_BASE_PATH) is not writable."; \
		exit 1; \
	fi
	@echo "✓ Workspace ready and writable"

validate: ## Validate environment variables and connectivity
	@echo "→ Validating environment..."
	@if [ -z "$(LLM_BASE_URL)" ]; then echo "❌ Error: LLM_BASE_URL is not set in .env"; exit 1; fi
	@echo "  ✓ LLM_BASE_URL set to $(LLM_BASE_URL)"
	@if ! curl -s --connect-timeout 5 $(LLM_BASE_URL)/api/tags > /dev/null; then \
		echo "❌ Error: LLM_BASE_URL ($(LLM_BASE_URL)) is not reachable."; \
		exit 1; \
	fi
	@echo "  ✓ LLM_BASE_URL is reachable"
	@echo "✓ Environment validation successful"

health: ## Check backend health
	@curl -s http://localhost:8000/health | python -m json.tool || echo "Backend not running"

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
