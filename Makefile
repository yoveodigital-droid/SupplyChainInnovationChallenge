.DEFAULT_GOAL := help
SHELL := /bin/bash

VENV       := .venv
PY         := $(VENV)/bin/python
PIP        := $(VENV)/bin/pip
UVICORN    := $(VENV)/bin/uvicorn
PYTEST     := $(VENV)/bin/pytest
BACKEND    := backend
FRONTEND   := frontend
API_PORT   ?= 8000
WEB_PORT   ?= 5173

.PHONY: help
help: ## Show this help
	@echo "PortPulse — demo commands"
	@echo
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "  First run:  make setup && make dev"

# --------------------------------------------------------------------------- #

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip

.PHONY: setup
setup: $(VENV)/bin/activate ## Install backend and frontend dependencies (needs network once)
	$(PIP) install --quiet -r $(BACKEND)/requirements.txt
	cd $(FRONTEND) && npm install --no-audit --no-fund
	@echo "Dependencies installed. Run 'make dev'."

.PHONY: seed
seed: ## Build the deterministic demo database
	cd $(BACKEND) && ../$(PY) -m app.seed

.PHONY: reseed
reseed: ## Rebuild the database and retrain the model from scratch
	cd $(BACKEND) && ../$(PY) -m app.seed --force

.PHONY: train
train: seed ## Train (or reuse) the forecaster and print its holdout scores
	cd $(BACKEND) && ../$(PY) -c "from app.db import session_scope; \
	from app.services.forecast import get_bundle; \
	from contextlib import suppress; \
	db = session_scope().__enter__(); b = get_bundle(db); \
	print('rows', b.trained_rows, 'through', b.trained_through); \
	print({k: round(v, 3) for k, v in b.metrics.items()})"

.PHONY: dev
dev: seed ## Run backend + frontend together (Ctrl-C stops both)
	@echo "API  → http://localhost:$(API_PORT)/docs"
	@echo "Demo → http://localhost:$(WEB_PORT)"
	@trap 'kill 0' EXIT INT TERM; \
	( cd $(BACKEND) && ../$(UVICORN) app.main:app --port $(API_PORT) --host 0.0.0.0 ) & \
	( cd $(FRONTEND) && npm run dev -- --port $(WEB_PORT) ) & \
	wait

.PHONY: api
api: seed ## Run only the backend
	cd $(BACKEND) && ../$(UVICORN) app.main:app --reload --port $(API_PORT)

.PHONY: web
web: ## Run only the frontend
	cd $(FRONTEND) && npm run dev -- --port $(WEB_PORT)

.PHONY: test
test: ## Run the backend test suite and the frontend smoke tests
	cd $(BACKEND) && ../$(PYTEST)
	cd $(FRONTEND) && npm run test

.PHONY: test-backend
test-backend: ## Run only the pytest suite
	cd $(BACKEND) && ../$(PYTEST)

.PHONY: build
build: ## Type-check and build the production frontend bundle
	cd $(FRONTEND) && npm run build

.PHONY: preview
preview: ## Record the API and build the self-contained hosted preview
	$(PY) scripts/record_preview.py
	cd $(FRONTEND) && node scripts/build-preview.mjs
	@echo "Open preview/portpulse-preview.html or publish it as an artifact."

.PHONY: demo-check
demo-check: ## Replay the scripted §7 demo against a running API and print each beat
	$(PY) scripts/demo_check.py

.PHONY: clean
clean: ## Remove the generated database, trained model and build output
	rm -rf $(BACKEND)/data $(FRONTEND)/dist $(FRONTEND)/dist-preview preview
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
