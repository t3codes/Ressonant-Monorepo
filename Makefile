default: help

# APP aceita o nome da pasta (ressonant_backend) ou o nome curto do serviço (backend).
# Convenção: apps/ressonant_<nome>/ expõe o serviço Compose <nome>.
APP_DIR := $(firstword $(wildcard apps/$(APP) apps/ressonant_$(APP)))
SERVICE := $(patsubst ressonant_%,%,$(notdir $(APP_DIR)))
COMPOSE := docker compose

.PHONY: help setup env check-app check-env infra-up infra-down observability-up observability-down \
	up down build logs ps migrate prod-init test lint check-structure lint-check format-check typecheck hooks check

help: # Show help for each of the makefile recipes.
	@grep -E '^[a-zA-Z0-9/ -]+:.*#' Makefile | sort | while read -r l; do \
		target=$$(echo $$l | cut -f 1 -d':'); \
		description=$$(echo $$l | cut -f 2- -d'#'); \
		formatted_target=$$(echo $$target | sed 's/ / | /g'); \
		printf "\033[1;32m%-20s\033[00m %s\n" "$$formatted_target:" "$$description"; \
	done
	@echo; echo "Targets por app usam APP=<nome>, ex.: make up APP=backend (apps: $$(ls apps | sed 's/^ressonant_//' | tr '\n' ' '))"

check-app:
	@[ -n "$(APP)" ] || { echo "Informe o app: make $(MAKECMDGOALS) APP=<nome> (ex.: APP=backend)"; exit 2; }
	@[ -n "$(APP_DIR)" ] || { echo "App '$(APP)' não encontrado em apps/. Disponíveis: $$(ls apps | tr '\n' ' ')"; exit 2; }

check-env:
	@[ -f .env ] || { echo ".env ausente na raiz: rode 'make setup'"; exit 2; }
	@for d in apps/*/; do [ -f "$$d.env.example" ] && [ ! -f "$${d}.env" ] && { echo "$${d}.env ausente: rode 'make setup'"; exit 2; }; done; true

setup: # Create .env files (with a random AUTH_SECRET), install locked deps and pre-commit hooks.
	@[ -f .env ] || { cp .env.example .env; echo "criado .env"; }
	@for d in apps/*/; do \
		if [ -f "$$d.env.example" ] && [ ! -f "$${d}.env" ]; then \
			cp "$$d.env.example" "$${d}.env"; \
			sed -i "s|^AUTH_SECRET=.*|AUTH_SECRET=$$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')|" "$${d}.env"; \
			echo "criado $${d}.env"; \
		fi; \
	done
	uv sync --locked --all-groups --all-packages
	uvx pre-commit install

env: # Run "make env" in each app, ignoring failures.
	@for dir in apps/*/; do \
		$(MAKE) -C "$$dir" env || true; \
	done

infra-up: check-env # Start shared infrastructure (Postgres and Redis) and wait until healthy.
	$(COMPOSE) up -d --wait postgres redis

infra-down: # Stop shared infrastructure (data volumes are kept).
	$(COMPOSE) stop postgres

observability-up: check-env # Start OTel Collector, Tempo, Prometheus and Grafana.
	$(COMPOSE) up -d --wait otel-collector tempo prometheus grafana
	@echo "Grafana: http://localhost:$${GRAFANA_PORT:-$$(sed -n 's/^GRAFANA_PORT=//p' .env)} (credenciais no .env: GRAFANA_ADMIN_USER / GRAFANA_ADMIN_PASSWORD)"

observability-down: # Stop the observability stack (data volumes are kept).
	$(COMPOSE) stop grafana prometheus tempo otel-collector

up: check-app check-env # Build and start an app plus its dependencies: make up APP=backend
	$(COMPOSE) up -d --build --wait $(SERVICE)

down: check-app # Stop an app (containers removed, data kept): make down APP=backend
	$(COMPOSE) rm -sf $(SERVICE)

build: check-app check-env # Build an app image only: make build APP=backend
	$(COMPOSE) build $(SERVICE)

logs: check-app # Follow an app's logs: make logs APP=backend
	$(COMPOSE) logs -f --tail=100 $(SERVICE)

ps: # List running containers of the monorepo.
	$(COMPOSE) ps

migrate: check-app check-env # Run the app's migrations in Docker: make migrate APP=backend
	$(COMPOSE) run --rm --no-deps migrate

prod-init: check-app check-env # Bootstrap idempotente: migrate/apply → create-admin → seed-prod-catalog.
	$(MAKE) -C $(APP_DIR) migrate/apply
	$(MAKE) -C $(APP_DIR) migrate/create-admin
	$(MAKE) -C $(APP_DIR) seed-prod-catalog

test: # Run tests: all projects, or one app with APP=<nome>.
ifneq ($(APP),)
	@$(MAKE) --no-print-directory check-app APP=$(APP)
	$(MAKE) -C $(APP_DIR) test
else
	@status=0; \
	for dir in packages/*/ apps/*/; do \
		[ -d "$${dir}tests" ] || continue; \
		echo "==> pytest $${dir}tests"; \
		(cd "$$dir" && uv run pytest tests); s=$$?; \
		if [ $$s -ne 0 ] && [ $$s -ne 5 ]; then status=$$s; fi; \
	done; \
	exit $$status
endif

lint: # Lint and format with autofix (whole workspace).
	uv run ruff check --fix . && uv run ruff format .

check-structure: # Verify the app structure of every app.
	@for dir in apps/*/; do $(MAKE) --no-print-directory -C "$$dir" check-structure || exit 1; done

lint-check: # Lint without writing files.
	uv run ruff check .

format-check: # Check formatting without writing files.
	uv run ruff format --check .

typecheck: # Run mypy on the policy hooks.
	uv run mypy

hooks: # Policy checks (PEP 420 common namespace, requires-python).
	python3 hooks/check_no_common_init.py
	python3 hooks/check_requires_python_consistent.py

check: # Full local gate: lint, format, types, tests, policy hooks.
	$(MAKE) lint-check
	$(MAKE) format-check
	$(MAKE) typecheck
	$(MAKE) test
	$(MAKE) hooks
