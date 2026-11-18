default: help

APP_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
ROOT := $(abspath $(APP_DIR)/../..)
COMPOSE := docker compose --project-directory $(ROOT)
RUN := uv run --project $(ROOT) --directory $(APP_DIR)

.PHONY: help env setup up test test-integration lint check-structure migrate/generate migrate/apply migrate/create-admin export-openapi \
	docker/up dup docker/down ddown docker/build dbuild docker/logs dlogs docker/migrate dmigrate \
	ci/setup ci/lint ci/tests

help: # Show help for each of the makefile recipes.
	@grep -E '^[a-zA-Z0-9/ -]+:.*#' Makefile | sort | while read -r l; do \
		target=$$(echo $$l | cut -f 1 -d':'); \
		description=$$(echo $$l | cut -f 2- -d'#'); \
		formatted_target=$$(echo $$target | sed 's/ / | /g'); \
		printf "\033[1;32m%-20s\033[00m %s\n" "$$formatted_target:" "$$description"; \
	done

env: # Create .env from .env.example when missing.
	@[ -f $(APP_DIR)/.env ] || cp $(APP_DIR)/.env.example $(APP_DIR)/.env

setup: env # Install locked workspace dependencies.
	cd $(ROOT) && uv sync --locked --all-groups --all-packages

up: # Run the API locally with reload (needs Postgres, see docker/up).
	set -a; . $(APP_DIR)/.env; set +a; $(RUN) uvicorn app.main:app --reload --port 8000

test: # Run the test suite.
	$(RUN) pytest tests

test-integration: # Integration tests against a running API: API_BASE_URL=http://localhost:8000 make test-integration.
	@[ -n "$$API_BASE_URL" ] || { echo 'Defina API_BASE_URL (ex.: http://localhost:8000)'; exit 2; }
	$(RUN) pytest tests/integration

lint: # Lint and format with autofix.
	$(RUN) ruff check --fix . && $(RUN) ruff format .

check-structure: # Verify the app structure.
	$(RUN) check-structure

migrate/generate: # Generate a migration: make migrate/generate msg="<description>".
	@[ -n "$(msg)" ] || { echo 'msg is required: make migrate/generate msg="<description>"'; exit 1; }
	set -a; . $(APP_DIR)/.env; set +a; $(RUN) alembic revision --autogenerate -m "$(msg)"

migrate/apply: # Apply migrations to the database in .env.
	set -a; . $(APP_DIR)/.env; set +a; $(RUN) alembic upgrade head

migrate/create-admin: # Create the first admin (ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_CPF in .env).
	set -a; . $(APP_DIR)/.env; set +a; $(RUN) python -m app.scripts.create_admin

export-openapi: # Export OpenAPI to openapi.json (spec versionada).
	PYTHONPATH=$(APP_DIR) $(RUN) python scripts/export_openapi.py $(APP_DIR)/openapi.json

docker/up dup: env # Start the API (and Postgres, migrations) in Docker.
	$(COMPOSE) up -d --build --wait backend

docker/down ddown: # Stop the API container (Postgres and data are kept).
	$(COMPOSE) rm -sf backend

docker/build dbuild: # Build the API image.
	$(COMPOSE) build backend

docker/logs dlogs: # Follow the API logs.
	$(COMPOSE) logs -f backend

docker/migrate dmigrate: # Apply migrations with the one-shot migrate service.
	$(COMPOSE) run --rm --no-deps migrate

ci/setup: # Prepare the CI runner.
	command -v uv >/dev/null || python3 -m pip install uv
	cd $(ROOT) && uv sync --locked --all-groups --all-packages

ci/lint: # Lint and format check without writing files.
	$(RUN) ruff check . && $(RUN) ruff format --check .

ci/tests: # Run the test suite in CI.
	$(MAKE) test
