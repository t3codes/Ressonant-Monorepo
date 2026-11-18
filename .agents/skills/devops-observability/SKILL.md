---
name: devops-observability
description: Infraestrutura local, Docker, Docker Compose, CI/CD e observabilidade do Ressonant (OpenTelemetry, OTel Collector, Tempo, Prometheus, Grafana). Use ao subir ou depurar containers, alterar Dockerfile ou compose, mexer em healthchecks, variáveis OTEL_*, dashboards e datasources do Grafana, workflows do GitHub Actions, ou ao investigar por que métricas/traces não aparecem.
metadata:
  scope: infra
  language: pt-BR
---

# devops-observability

Siga a infraestrutura **real**. Leia o arquivo antes de alterá-lo; mudanças aqui afetam todos os apps.

## Topologia (implementado)

```
docker-compose.yml (índice, include:)
├── infra/docker-compose.yml                  postgres:15-alpine (volume ressonant_backend_pg-data)
├── infra/observability/docker-compose.yml    otel-collector, tempo, prometheus, grafana
└── apps/ressonant_backend/docker-compose.yml migrate (one-shot) + backend
```

- Redes: `data` (postgres + apps com banco) e `telemetry` (collector, Tempo, Prometheus, Grafana + apps instrumentadas).
- Portas só em `127.0.0.1`: API 8000, Postgres 5432, Grafana 3001, Prometheus 9090, OTLP/HTTP 4318 (todas parametrizadas no `.env` da raiz).
- Variáveis: `.env` da raiz (infra) e `apps/<app>/.env` (app); modelos em `.env.example`. Nunca versionar `.env` nem valores reais.
- **Volumes de dados nunca são removidos** por `make down`/`infra-down`. O volume do Postgres tem nome legado de propósito (`ressonant_backend_pg-data`). Não rode `docker compose down -v`, `docker volume rm` ou `prune` sem pedido explícito do usuário.

## Comandos (da raiz)

```bash
make setup                    # cria .env (raiz e apps) e instala deps
make infra-up                 # Postgres, espera ficar healthy
make observability-up         # collector, Tempo, Prometheus, Grafana
make up APP=backend           # build + migrate + backend (--wait)
make down APP=backend         # remove o container do app; dados ficam
make build APP=backend | make logs APP=backend | make ps
make migrate APP=backend      # serviço one-shot `migrate`
make observability-down | make infra-down
docker compose config -q      # valida o compose
```

## Dockerfile do backend

Multi-stage (`manifests` → `builder` → `runtime`), contexto = **raiz** do monorepo. O estágio `manifests` leva só os `pyproject.toml` das apps irmãs para o `uv.lock` fechar (`uv sync --locked`), então o build de um app não depende do código dos outros. Execução como usuário não-root (`uid 10001`), `HEALTHCHECK` em `/health`, `CMD` com `opentelemetry-instrument uvicorn app.main:app`. O `.dockerignore` é deny-by-default (whitelist por app). Mudou `pyproject.toml` ou lock? Rode `uv lock --check` e rebuild.

## Telemetria (implementado)

`app → OTLP/HTTP → otel-collector (traces → Tempo; métricas → exporter Prometheus :8889) → Prometheus (scrape 10s) → Grafana`.

Contrato do app (modelo em `apps/ressonant_backend/.env.example`): `OTEL_SERVICE_NAME` (único por processo), `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`, `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_TRACES_EXPORTER=otlp_proto_http`, `OTEL_METRICS_EXPORTER=otlp_proto_http`, `OTEL_LOGS_EXPORTER=none`, `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=logging`. Sem esse conjunto a exportação falha em silêncio. `uvicorn --reload` roda **sem** telemetria. **Não** escreva `telemetry.py`; instrumentors vivem em `common-telemetry`.

Métricas HTTP chegam como `http_server_duration_milliseconds_{bucket,count,sum}` com labels `service_name`, `http_method`, `http_status_code`, `http_target`; também `http_server_active_requests` e `db_client_connections_usage`. Logs saem em JSON no stdout com `trace_id`/`span_id`.

Grafana (`GRAFANA.md` na raiz): datasources `Prometheus` (uid `prometheus`) e `Tempo` (uid `tempo`) e dashboard `ressonant-backend` são **provisionados por arquivo** em `infra/observability/grafana/`; edite o JSON/YAML no repo, não pela UI.

## Diagnóstico (ordem)

1. `make ps` e `docker compose logs <serviço>`; healthchecks (`/health`, `/health/ready`).
2. Sem métricas: `curl -s localhost:9090/api/v1/targets` (alvo `otel-collector` deve estar `up`); `curl -s 'localhost:9090/api/v1/query?query=http_server_duration_milliseconds_count'`.
3. Sem traces: `docker compose logs otel-collector tempo`; busca `{ resource.service.name = "ressonant_backend" }` no Explore → Tempo.
4. Sem nada: confira as variáveis `OTEL_*` no container (`docker compose exec backend env | grep OTEL`).
5. Grafana: `curl -u <user>:<senha> localhost:3001/api/datasources` (credenciais no `.env`).

O teste de health do datasource Tempo retorna 404 no Grafana 11.1 (limitação do plugin); valide pela busca de traces.

## CI/CD (parcial)

Existem: `pr-checks.yaml` (matrix de apps → `test-and-lint-app.yaml`: `make ci/setup`, `ci/lint`, `ci/tests`), `integration-test-*.yaml` e `gitstream.yml`. Os workflows de **deploy foram removidos** (`docs/ci-cd.md`); não há deploy configurado. As integrações dependem de `deploy-config.yaml` por app e de targets `ci/integration-test` que o backend **não** possui. Não apresente isso como pronto. Para diagnosticar falha de CI com `gh`, a skill externa `gh-fix-ci` (se instalada) pode ajudar.

## Não existe (não afirmar)

Loki/logs via OTLP, alertas, Alloy, Pyroscope, deploy, Kubernetes/Helm neste repo, Redis, fila.

## Skills externas instaladas relacionadas

`tempo` (TraceQL; ignore os passos de `git clone`/`docker compose up` do exemplo, o Tempo já sobe pelo compose), `opentelemetry` (foco em Grafana Cloud; ignore Java/.NET/Operator e `pip install`: aqui o pacote é `common-telemetry`), `python-observability` (logging estruturado e métricas). Nunca execute comandos de skills de terceiros que baixem código ou subam serviços sem confirmar com o usuário.
