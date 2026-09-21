# Job Application Tracker - developer tasks.
# Usage: run `make help` to see available commands.

ifeq ($(OS),Windows_NT)
	VENV_BIN := backend/.venv/Scripts
	PYTHON := python
else
	VENV_BIN := backend/.venv/bin
	PYTHON := python3
endif

.DEFAULT_GOAL := help

.PHONY: help setup install-backend install-frontend backend frontend dev \
        build app dist docker-up docker-down clean

help: ## Show this help
	@echo Job Application Tracker - available commands:
	@echo   make setup       Install backend + frontend dependencies (run once)
	@echo   make app         BUILD frontend then launch tray app  (normal usage)
	@echo   make dist        Build a standalone AppTracker.exe (PyInstaller)
	@echo   make dev         Run backend and frontend dev servers (contributors)
	@echo   make build       Production build of the frontend only
	@echo   make backend     Run only the backend (http://localhost:8000)
	@echo   make frontend    Run only the frontend dev server (http://localhost:5173)
	@echo   make docker-up   Start everything with Docker Compose
	@echo   make docker-down Stop the Docker Compose stack
	@echo   make clean       Remove venv, node_modules and build artifacts

setup: install-backend install-frontend ## Install all dependencies

install-backend: ## Create venv and install backend deps
	$(PYTHON) -m venv backend/.venv
	$(VENV_BIN)/python -m pip install --upgrade pip
	$(VENV_BIN)/python -m pip install -r backend/requirements.txt

install-frontend: ## Install frontend deps
	cd frontend && npm install

backend: ## Run the backend API server
	$(VENV_BIN)/uvicorn app.main:app --reload --port 8000 --app-dir backend

frontend: ## Run the frontend dev server
	cd frontend && npm run dev

dev: ## Run backend and frontend at the same time
	@$(MAKE) -j2 backend frontend

build: ## Build the frontend for production
	cd frontend && npm run build

app: build ## Build frontend then launch the tray app (normal end-user usage)
	$(VENV_BIN)/python backend/launcher.py

dist: build ## Package a standalone Windows exe via PyInstaller
	$(VENV_BIN)/python -m pip install pyinstaller
	$(VENV_BIN)/python backend/scripts/make_icon.py
	$(VENV_BIN)/pyinstaller --noconfirm backend/apptracker.spec

docker-up: ## Start the full stack with Docker
	docker compose up --build

docker-down: ## Stop the Docker stack
	docker compose down

clean: ## Remove dependencies and build artifacts
	rm -rf backend/.venv backend/__pycache__ frontend/node_modules frontend/dist frontend/dist-types build dist *.spec.bak
