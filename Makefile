SHELL := /bin/bash
PY    := backend/.venv/bin/python
HOST  ?= 127.0.0.1
PORT  ?= 8080

.PHONY: setup dev run build test check services fake-voice avatar clean

setup: ## Create the Python venv and install backend + frontend deps
	test -d backend/.venv || python3 -m venv backend/.venv
	$(PY) -m pip install -q -e 'backend[dev]'
	cd frontend && npm install --no-fund --no-audit

dev: ## Gateway (hot reload) on :8080 + Vite dev server on :5173
	@echo "UI: http://127.0.0.1:5173   API: http://$(HOST):$(PORT)"
	@trap 'kill 0' EXIT; \
	(cd backend && .venv/bin/uvicorn app.main:app --host $(HOST) --port $(PORT) --reload) & \
	(cd frontend && npm run dev) & \
	wait

build: ## Build the UI into frontend/build (served by the gateway)
	cd frontend && npm run build

run: build ## Production-style: one server on http://127.0.0.1:8080
	cd backend && .venv/bin/uvicorn app.main:app --host $(HOST) --port $(PORT)

test: ## Backend + frontend unit tests
	cd backend && .venv/bin/python -m pytest -q
	cd frontend && npm test

check: test ## Tests + Svelte/TS type check
	cd frontend && npm run check

services: ## Check Ollama + VoiceStudio are reachable
	./scripts/check_services.sh

fake-voice: ## Stand-in VoiceStudio on :3900 (tones instead of speech) for dev/testing
	$(PY) scripts/fake_voicestudio.py

avatar: ## Regenerate the placeholder idle.png / talking.gif
	$(PY) scripts/make_placeholder_avatar.py

clean:
	rm -rf frontend/build frontend/.svelte-kit
