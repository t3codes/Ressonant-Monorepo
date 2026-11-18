# syntax=docker/dockerfile:1
# Contexto de build: raiz do monorepo.
#   docker build -f apps/ressonant_backend/Dockerfile .

# O uv.lock cobre todos os membros do workspace (apps/*). Para o lock bater sem copiar o código das
# apps irmãs, levamos só os pyproject.toml delas: o build deste app não depende dos demais.
FROM alpine:3.20 AS manifests
COPY apps /src/apps
RUN find /src/apps -type f ! -name pyproject.toml -delete \
    && find /src/apps -mindepth 1 -type d -empty -delete

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /monorepo

COPY pyproject.toml uv.lock ./
COPY --from=manifests /src/apps ./apps
COPY packages ./packages
# Camada de dependências de terceiros: só invalida quando o lock ou os manifests mudam.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package ressonant_backend --no-install-workspace
COPY apps/ressonant_backend ./apps/ressonant_backend
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package ressonant_backend

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/monorepo/.venv/bin:$PATH"
RUN useradd --system --uid 10001 --no-create-home app
WORKDIR /monorepo
# O venv referencia as libs em packages/ (instalação editável do workspace).
COPY --from=builder /monorepo/.venv ./.venv
COPY --from=builder /monorepo/packages ./packages
COPY --from=builder /monorepo/apps/ressonant_backend ./apps/ressonant_backend
WORKDIR /monorepo/apps/ressonant_backend
USER app

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]
CMD ["opentelemetry-instrument", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
