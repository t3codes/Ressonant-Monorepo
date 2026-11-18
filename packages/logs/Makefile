default: help

ROOT := $(shell git rev-parse --show-toplevel)
LIB_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
LIB_REL := $(subst $(ROOT)/,,$(LIB_DIR))
UV_IMAGE := ghcr.io/astral-sh/uv:python3.13-bookworm-slim

.PHONY: help setup test docker/test dtest

docker/test dtest: # Run the library tests inside a container.
	docker run --rm -v $(ROOT):/monorepo -w /monorepo/$(LIB_REL) $(UV_IMAGE) \
		uv run --project /monorepo pytest tests

help: # Show help for each of the makefile recipes.
	@grep -E '^[a-zA-Z0-9/ -]+:.*#' Makefile | sort | while read -r l; do \
		target=$$(echo $$l | cut -f 1 -d':'); \
		description=$$(echo $$l | cut -f 2- -d'#'); \
		formatted_target=$$(echo $$target | sed 's/ / | /g'); \
		printf "\033[1;32m%-20s\033[00m %s\n" "$$formatted_target:" "$$description"; \
	done

setup: # Install locked deps for the workspace.
	uv sync --locked --all-groups --all-packages

test: # Run the library tests (tolerates "no tests collected").
	uv run --project $(ROOT) pytest tests || [ $$? -eq 5 ]
