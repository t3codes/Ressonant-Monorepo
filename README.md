# Introdução

Monorepo (UV workspace Python) do ecossistema **Ressonant**: bibliotecas compartilhadas em `packages/*`, aplicações em `apps/*`, infraestrutura local em `infra/`. Cada app builda, sobe, testa e é mantida de forma independente.

# Propósito

Cópia exata de um clone do Slack com capacidades agênticas: canais e threads, mensagens e execução autônoma de fluxos por agentes de IA. Hoje o backend cobre **autenticação e CRUD de usuários**.

# Arquitetura

```
apps/ressonant_backend/    FastAPI + PostgreSQL (routes → services → repository → models)
packages/                  libs Python compartilhadas (common-errors, common-logs, common-telemetry, ...)
infra/                     Postgres compartilhado e stack de observabilidade
docker-compose.yml         índice que agrega os composes de infra/ e de cada app
Makefile                   interface única: make help
```

```mermaid
flowchart LR
    client[Cliente] --> backend
    subgraph data[rede data]
        backend --> postgres[(PostgreSQL)]
    end
    subgraph telemetry[rede telemetry]
        backend -- OTLP/HTTP --> otel[OTel Collector]
        otel --> tempo[Tempo]
        otel --> prom[Prometheus]
        grafana[Grafana] --> tempo
        grafana --> prom
    end
```

Decisões:

- **Um compose por unidade, agregado na raiz por `include:`**: a raiz não define serviços, então apps não se acoplam. `docker compose up -d backend` sobe só o backend e suas dependências. Detalhes em [`docs/docker-compose.md`](docs/docker-compose.md).
- **Postgres e observabilidade são infra compartilhada** (`infra/`), em redes separadas (`data`, `telemetry`); cada app entra só nas redes de que precisa.
- **Build independente por app**: o `Dockerfile` de cada app usa a raiz como contexto e leva só os manifests das apps irmãs para o `uv.lock` fechar.
- **Migration como serviço one-shot** (`migrate`): o backend só sobe depois de ela terminar com sucesso.

# Pré-requisitos

- Docker com Compose v2
- [uv](https://docs.astral.sh/uv/) e `make`
- Python 3.13 (o uv instala se necessário)

# Quick Start

```bash
make setup                # cria .env (raiz e apps), instala deps e pre-commit
make infra-up             # PostgreSQL
make up APP=backend       # builda, migra e sobe o backend
curl localhost:8000/health/ready
```

API em <http://localhost:8000>, Swagger em <http://localhost:8000/docs>. `make help` lista todos os targets.

# Estado atual: o que está implementado

- **Implementado** (`apps/ressonant_backend`): health check (`GET /health`, `GET /health/ready`), autenticação (`POST /auth/register`, `POST /auth/login`, `GET /auth/me`) e CRUD completo de usuários (`POST /users`, `GET /users`, `GET /users/{user_id}`, `PUT /users/{user_id}`, `PATCH /users/{user_id}/status`, `DELETE /users/{user_id}`).
- **Planejado** (sem código): canais, threads, mensagens, tempo real (WebSocket), Redis, mensageria, execução de fluxos por agentes de IA, RAG, mail, notificações, presença, busca, preferências, boards/sprints e refresh token/rate limit.

Rotas implementadas hoje (contrato versionado em `apps/ressonant_backend/openapi.json`):

| Método | Rota | Descrição |
| --- | --- | --- |
| GET | `/health` | Liveness |
| GET | `/health/ready` | Readiness (checa o banco) |
| POST | `/auth/register` | Cadastro público |
| POST | `/auth/login` | Login (retorna access token JWT) |
| GET | `/auth/me` | Dados do usuário autenticado |
| POST | `/users` | Cria usuário (admin) |
| GET | `/users` | Lista usuários (paginação/filtro, admin) |
| GET | `/users/{user_id}` | Busca (admin ou o próprio usuário) |
| PUT | `/users/{user_id}` | Atualiza (admin ou o próprio usuário) |
| PATCH | `/users/{user_id}/status` | Ativa/desativa (admin) |
| DELETE | `/users/{user_id}` | Soft delete (admin) |

> O frontend (Ressonant) ainda não consome esse backend: a camada de dados de chat, kanban, mail, notificações e tempo real permanece em mock (`localStorage`) por trás dos contratos em `src/repositories/contracts.ts` do frontend.

## Como iniciar o backend (local, sem Docker)

```bash
make setup            # cria .env (raiz e apps) com AUTH_SECRET, instala deps
make infra-up         # sobe o PostgreSQL
make migrate APP=backend   # roda as migrations (alembic upgrade head)
make up APP=backend   # sobe a API (uvicorn) em http://localhost:8000
curl localhost:8000/health/ready
```

Ou via Docker Compose: `docker compose up -d backend` (o compose sobe migrate + backend). Swagger: <http://localhost:8000/docs>.

## Configuração

`make setup` copia os `.env.example` (fonte de verdade das variáveis) e gera um `AUTH_SECRET` aleatório. Nada com segredo é versionado.

| Arquivo | Conteúdo |
| --- | --- |
| [`.env.example`](.env.example) | `POSTGRES_*`, portas, credenciais do Grafana |
| [`apps/ressonant_backend/.env.example`](apps/ressonant_backend/.env.example) | `AUTH_SECRET`, CORS, `OTEL_*`, admin inicial |

## Comandos do dia a dia

`APP` aceita `backend` ou `ressonant_backend`.

| Tarefa | Comando |
| --- | --- |
| Subir só o Postgres | `make infra-up` |
| Subir / parar um app | `make up APP=backend` / `make down APP=backend` |
| Build isolado | `make build APP=backend` |
| Logs | `make logs APP=backend` |
| Status | `make ps` |
| Migrations no Docker | `make migrate APP=backend` |
| Testes de um app / de tudo | `make test APP=backend` / `make test` |
| Gate completo (lint, format, types, testes) | `make check` |
| Criar o primeiro admin | `make -C apps/ressonant_backend migrate/create-admin` (preencha `ADMIN_*` no `.env`) |
| Nova migration | `make -C apps/ressonant_backend migrate/generate msg="..."` |

Equivalentes em Compose puro (da raiz): `docker compose up -d postgres`, `docker compose up -d backend`, `docker compose build backend`, `docker compose logs -f backend`, `docker compose stop backend`, `docker compose down`.

Nenhum desses comandos remove volumes: os dados do Postgres persistem em `ressonant_backend_pg-data`.

## Testes

- Unitários (SQLite em memória, sem Docker): `make test APP=backend`.
- Integração real contra API + Postgres no ar: `API_BASE_URL=http://localhost:8000 make -C apps/ressonant_backend test-integration`.

## Observabilidade (Grafana)

```bash
make observability-up     # collector, Tempo, Prometheus, Grafana
make up APP=backend       # gera telemetria
```

| | |
| --- | --- |
| Grafana | <http://localhost:3001> |
| Usuário / senha (só dev local) | `admin` / `ressonant-dev` (`GRAFANA_ADMIN_*` no `.env`) |
| Prometheus | <http://localhost:9090> |

Datasources (Prometheus, Tempo) e o dashboard **Ressonant → Ressonant Backend** já vêm provisionados. Como verificar a telemetria, configurar novas apps e troubleshooting: [`GRAFANA.md`](GRAFANA.md).

## Collections da API

As collections Postman ficam fora do monorepo, em `../ressonant-api-collections` (README próprio, gerada do `openapi.json` do backend).

# Adicionar um novo app

Checklist em [`docs/docker-compose.md`](docs/docker-compose.md#adicionar-uma-app): pasta `apps/ressonant_<nome>/` com `Dockerfile`, `docker-compose.yml`, `.env.example` e `Makefile`; include no compose da raiz; liberar no `.dockerignore`. Estrutura interna de apps Python: [`docs/guides/app-structure.md`](docs/guides/app-structure.md); libs: [`packages/README.md`](packages/README.md).

# Troubleshooting

| Sintoma | Correção |
| --- | --- |
| `defina POSTGRES_PASSWORD no .env` ou `.env ausente` | `make setup` |
| `App 'x' não encontrado` | use `APP=backend` (nomes: `ls apps`) |
| Porta 5432/8000/3001 em uso | ajuste `POSTGRES_PORT`/`BACKEND_PORT`/`GRAFANA_PORT` no `.env` |
| Backend não sobe | `make logs APP=backend`; a migration roda antes: `docker compose logs migrate` |
| `AUTH_SECRET deve ter ao menos 32 caracteres` | preencha no `apps/ressonant_backend/.env` (`make setup` gera) |
| Senha do Postgres recusada | o volume guarda a senha da primeira criação; use a mesma em `POSTGRES_PASSWORD` |
| `uv sync --locked` falha | `uv lock` e commite o `uv.lock` |

# Deploy

Não documentado nesta fase; seguir o README de cada membro em `apps/` ou `packages/` quando existir.

# Read more

- [`GRAFANA.md`](GRAFANA.md): Grafana e telemetria
- [`apps/ressonant_backend/README.md`](apps/ressonant_backend/README.md): API
- [`docs/docker-compose.md`](docs/docker-compose.md): orquestração local
- [`docs/ci-cd.md`](docs/ci-cd.md): CI/CD
- [`docs/adrs/0001-http-snake-case.md`](docs/adrs/0001-http-snake-case.md): snake_case no contrato HTTP
