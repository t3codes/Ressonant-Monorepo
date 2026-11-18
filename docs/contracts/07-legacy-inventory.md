# Inventário do Legado × Catálogo de Contratos (Fase 1, Passo 2)

- Fonte de verdade: arquivos lidos em disco (`apps/ressonant_backend`). Zero invenção.
- Legado existe e está funcional: auth (register/login/me), users CRUD, health, PostgreSQL + Alembic, JWT HS256, Argon2id.
- Legenda: Implementado · Parcial · Inexistente.

## 1. O que existe no backend legado (evidência)

| Item | Arquivo:linha | Estado |
|------|---------------|--------|
| FastAPI app + lifespan (logging) | `app/main.py:25-64` | Implementado |
| Health `/health` e `/health/ready` | `app/main.py:50-59` | Implementado |
| CORSMiddleware (origens configuráveis) | `app/main.py:39-45` | Implementado |
| Auth router prefixo `/auth` | `app/auth/routes.py:12` | Implementado |
| `POST /auth/register` (público, usuário comum) | `app/auth/routes.py:15-20` | Implementado |
| `POST /auth/login` → TokenResponse | `app/auth/routes.py:23-29` | Implementado |
| `GET /auth/me` (Bearer obrigatório) | `app/auth/routes.py:32-35` | Implementado |
| User router prefixo `/users` | `app/user/routes.py:17` | Implementado |
| `POST /users` (admin) | `app/user/routes.py:29-32` | Implementado |
| `GET /users` (admin, paginação skip/limit, filtro status_ativo) | `app/user/routes.py:35-50` | Implementado |
| `GET /users/{user_id}` (self ou admin) | `app/user/routes.py:53-57` | Implementado |
| `PUT /users/{user_id}` (self ou admin) | `app/user/routes.py:60-66` | Implementado |
| `PATCH /users/{user_id}/status` (admin) | `app/user/routes.py:69-74` | Implementado |
| `DELETE /users/{user_id}` (admin, soft delete) | `app/user/routes.py:77-80` | Implementado |
| JWT: create/decode access token (`sub`, `type=access`, `exp`, `iat`) | `app/auth/tokens.py:8-34` | Implementado |
| JWT extrai `sub` (user_id) do token — **nunca** da URL/body | `app/auth/deps.py:21-37` | Implementado |
| Senha Argon2id + hash de timing para e-mail inexistente | `app/common/security.py:9-21` | Implementado |
| Anti-enumeração login (mesma resposta usuário/senha inválida/inativo) | `app/auth/services.py:11-18` | Implementado |
| Validação CPF (dígitos verificadores) e telefone 10/11 | `app/user/schemas.py:14-49` | Implementado |
| Senha 8-128, idade 18-120, termos obrigatórios | `app/user/schemas.py:6-7,52-64` | Implementado |
| `senha_hash` nunca exposto em `UserResponse` | `app/user/schemas.py:100-112` | Implementado |
| Migration Alembic `0001_create_users` (tabela `users`, idx email único) | `migrations/versions/0001_create_users.py:16-43` | Implementado |
| `openapi.json` sincronizado (11 paths) | `openapi.json` | Implementado |
| exception handlers: CYB-001 corrigido (sem `input`/`exception` no log) | `packages/errors/src/common/errors/exception_handlers.py:35-78` | Implementado |
| Testes: auth 12, users ~15, log_leakage 3, exception_handlers 10 | `tests/` | Implementado |
| Settings: AUTH_SECRET/DATABASE_URL obrigatórios sem default; min 32 chars | `app/config/settings.py:22-43` | Implementado |
| docker-compose backend (migrate + backend, rede data/telemetry) | `apps/ressonant_backend/docker-compose.yml:1-29` | Implementado |
| Telemetria OTLP configurada (env vars, não código de setup) | `apps/ressonant_backend/.env.example:14-24` | Implementado |

## 2. Mapa domínio do catálogo × existência no legado

| Domínio (contrato mock) | Operações no catálogo | Existe no legado | Evidência / gap |
|-------------------------|----------------------|------------------|-----------------|
| Identity / Workspace / Auth | 29 | Parcial | register/login/me/users CRUD existem. **Workspaces inexistentes** (sem tabela, sem rota). Perfil User sem foto/avatar, sem presença/statusEmoji. |
| Chat (channels/conversations/messages) | 26 | Inexistente | Sem canais, conversas, mensagens, threads, WebSocket. |
| Reactions / Read-states / Notifications | 9 | Inexistente | Sem reações, estados de leitura, notificações. |
| Mail | 11 | Inexistente | Sem e-mail, pastas, threads, anexos. |
| Kanban boards/teams/columns | 2 | Inexistente | Sem times, boards, colunas, workflows, custom fields. |
| Kanban cards | 4 | Inexistente | Sem cards, subtarefas, checklist, comentários, histórico, worklogs, links, watchers. |

**Resumo:** o legado cobre somente Identity/Auth/Users. Todos os demais domínios do catálogo são inexistentes no código.

## 3. Stacks e infra (presente × ausente)

| Stack | Estado | Evidência |
|-------|--------|-----------|
| PostgreSQL + SQLAlchemy (síncrono, psycopg2) | Implementado | `app/database/engine.py`, migrations |
| Alembic migrations versionadas | Implementado | `migrations/versions/0001_create_users.py` |
| JWT HS256 access token | Implementado | `app/auth/tokens.py` |
| Argon2id | Implementado | `app/common/security.py` |
| Rate limit de login | **Ausente** | Nenhum middleware/limiter encontrado |
| Refresh token | **Ausente** | `tokens.py` só cria/decodifica access |
| Redis | **Ausente** | Sem dependência, sem compose |
| MinIO / S3 (fotos/anexos) | **Ausente** | Sem bucket, sem URL pré-assinada |
| WebSockets | **Ausente** | Sem rota `/ws`, sem dependência |
| Headers de segurança (HSTS, CSP, X-Frame-Options etc.) | **Ausente** | Apenas CORS em `main.py` |
| `/docs` protegido por ambiente | **Ausente** | FastAPI docs exposto por padrão |
| Logs estruturados JSON com trace_id | Implementado | `packages/logs`, `setup_logging` |
| Telemetria OTLP (traces/métricas) | Implementado (config env) | `.env.example` OTEL_* |

## 4. Inconsistências de formato e paridade (mock × legado)

| Campo/Formato | Mocks frontend | Legado backend | Ação necessária |
|---------------|----------------|----------------|-----------------|
| Case | camelCase (`userId`, `workspaceId`, `createdAt`) | snake_case (`user_id`, `workspace_id`, `criado_em`) | Mapeamento explícito nas rotas |
| IDs | prefixados (`user_*`, `ch_*`, `msg_*`, `card_*`, `board_*`, `team_*`) | UUID (`uuid4`, string) | Adapter de ID ou normalizar |
| Datas | ISO8601 strings | `DateTime(timezone=True)` + `func.now()` | Compatível (ISO no JSON) |
| `userId` na URL/body | parâmetro explícito nos contratos do mock | extraído do JWT via `CurrentUser` | Regra de ouro: JWT-only; rejeitar `userId` na URL nos novos endpoints |
| `readAt` | número / ISO / null (tipo misto) | — | Padronizar para ISO `date-time` |
| Senha/CPF | trafegam nos payloads de cadastro | `senha_hash` armazenado; CPF só dígitos | Nunca expor `senha_hash`; CPF validado e normalizado |
| `UserResponse` HTTP | name/handle/color/presence/workspaceIds esperados pelo frontend | id/email/cpf/telefone/idade/termos/status/interno_adm/criado/atualizado | Quebra de paridade: `mapUser` sintetiza defaults (`workspaceIds: []`) |

## 5. INEXISTENTE (não inventar como existente)

- WebSocket `/ws` — não há rota nem dependência.
- Redis, filas, pub/sub — não há dependência nem compose.
- MinIO/S3, anexos, fotos de perfil — não há bucket nem URL pré-assinada.
- Workspaces, teams, boards, columns, cards, kanban — não há tabela nem rota.
- Chat: canais, conversas, mensagens, reações, read-states — não há tabela nem rota.
- Mail: pastas, mensagens, anexos — não há tabela nem rota.
- Refresh token — não existe.
- Rate limit de login — não existe.
- Deploy CI/CD / Kubernetes / Helm — workflows removidos (AGENTS.md).
- Collection Postman versãoada no monorepo — `apps/ressonant_collections` existe como app não executável (coleção v2.1 Health/Auth/Users validadas contra openapi.json).

## 6. Recomendação de ordem de construção (rota por rota)

1. **Workspaces** (list/get) — dependência de kanban/mail/chat; baixa superfície sensível.
2. **Teams + membership** — necessária para kanban boards e controle de acesso.
3. **Kanban boards/columns** — depende de teams.
4. **Kanban cards** (`createCard` opcional hoje) — depende de boards/teams; maior complexidade (subtarefas, checklist, custom fields).
5. **Chat channels/conversations/messages** — depende de workspaces; WebSocket após REST.
6. **Reactions / Read-states / Notifications** — depende de messages.
7. **Mail** — depende de users/workspaces; anexos exigem MinIO (infra nova).

**Primeira rota recomendada:** `GET /workspaces` + `GET /workspaces/{id}` (somente leitura, JWT-only, sem body sensível) — valida o ciclo contrato → rota → QA → cyber → commit com menor risco.
