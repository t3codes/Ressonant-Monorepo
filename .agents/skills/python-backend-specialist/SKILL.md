---
name: python-backend-specialist
description: Desenvolvimento do backend Python/FastAPI do Ressonant (apps/ressonant_backend). Use ao criar ou alterar rotas, schemas, services, repositories, models SQLAlchemy, migrations Alembic, autenticação, autorização, settings ou tratamento de erros, e ao adicionar um novo módulo ou endpoint. Segue o layout e as convenções que existem hoje no código (síncrono, routes → services → repository → models), sem introduzir padrões novos.
metadata:
  scope: apps/ressonant_backend
  language: pt-BR
---

# python-backend-specialist

Trabalhe **dentro dos padrões que o código já usa**. Antes de editar, leia o módulo vizinho mais parecido (`app/user/` é a referência) e imite-o.

## Estado real (verifique antes de afirmar)

| Item | Estado |
|---|---|
| Stack | Python 3.13 (`==3.13.*`), FastAPI, Pydantic v2, SQLAlchemy 2, psycopg2, Alembic, PostgreSQL 15 |
| Modelo de execução | **Síncrono**: rotas `def`, `Session` síncrona. Async/WebSockets são só planejamento |
| Módulos | `app/auth`, `app/user`; transversais em `app/common`, `app/config`, `app/database` |
| Auth | JWT HS256 (`type=access`), Argon2id, bearer; sem refresh token, sem rate limit (pendências conhecidas) |
| Não existe ainda | WebSockets, Redis, mensageria, canais, mensagens, RAG |

## Layout e responsabilidades

```
app/<modulo>/
├── routes.py      # APIRouter fino: valida entrada, chama o service, devolve response_model
├── schemas.py     # Pydantic v2 (entrada e saída); validators de domínio (CPF, telefone, e-mail)
├── services.py    # regras de negócio e decisão de commit/rollback
├── repository.py  # única camada que fala com a Session (select/add/flush)
├── models.py      # SQLAlchemy 2 (Mapped/mapped_column), herda de app.database.engine.Base
└── deps.py        # dependências FastAPI (ex.: get_user_service)
```

- **Rota sem regra de negócio.** `routes.py` só orquestra (`service.metodo(...)` → `Response.model_validate`).
- **Repository não decide transação de negócio**: expõe `add` (com `flush`), `commit`, `rollback`; o **service** chama `commit`.
- **Concorrência de unicidade**: confira antes (`exists_by_...`) **e** trate `IntegrityError` com `rollback` e `ConflictException` (ver `UserService._create`).
- **Models** novos precisam ser importados em `app/main.py` e `migrations/env.py` (padrão `from app.<m> import models  # noqa: F401`) para entrar no metadata.
- **Queries**: sempre ORM/`select()` parametrizado; nunca interpolar string. Listagens paginam com `skip`/`limit` (`Query(ge=0)`, `Query(ge=1, le=100)`) e `order_by` determinístico (ver `UserRepository.list`).

## Configuração, erros e logs

- `app/config/settings.py`: `Settings` imutável lido do ambiente via `get_settings()` (cacheado). `DATABASE_URL` e `AUTH_SECRET` (≥ 32 caracteres) são obrigatórios; **nunca** dê default a segredo. Variável nova → documente no `apps/ressonant_backend/.env.example` (fonte de verdade).
- Erros: use `common.errors` (`ExceptionData(message=..., error_code=...)`, `NotFoundException`, `UnauthorizedException`, `ForbiddenException`, `BadRequestException`) com `is_expected=True` para erro de negócio. Conflitos usam `app.common.exceptions.ConflictException` (409). **Não** levante `HTTPException` crua. Handlers vêm de `setup_exception_handlers(app)`; o corpo de erro tem `status_code`, `message`, `error_code`, `detail`, `error_messages`. Cada erro novo tem `error_code` em `SCREAMING_SNAKE_CASE`.
- Logs: `common.logs` (structlog); `setup_logging()` roda no `lifespan`. Não crie `telemetry.py`: telemetria é do `opentelemetry-instrument` + `common-telemetry` (ver `AGENTS.md`).
- Segurança: respostas nunca incluem `senha_hash`; login devolve a **mesma resposta** para e-mail inexistente, senha errada e conta inativa; usuário inativo perde acesso mesmo com token válido; cadastro público nunca define flags administrativas. Mantenha essas garantias.

## Contrato HTTP

- **ADR 0001**: chaves **novas** em snake_case, sem `alias` camelCase. Contrato já publicado não se converte. Os nomes atuais em português (`senha`, `idade`, `termos_contrato`, `status_ativo`) são o contrato: não renomeie.
- Mudou rota, schema ou resposta? Atualize `openapi.json` (`make -C apps/ressonant_backend export-openapi`); o teste `test_openapi_sync` falha se ficar velho. Use a skill `qa-and-openapi`.

## Migrations

1. Altere o model.
2. `make -C apps/ressonant_backend migrate/generate msg="<descrição>"` (precisa de Postgres e do `.env`).
3. **Revise** o arquivo gerado em `migrations/versions/` (nome `<rev>_<slug>.py`; cobre `upgrade` e `downgrade`).
4. Aplique: `make -C apps/ressonant_backend migrate/apply`, ou `make migrate APP=backend` no Docker.
5. Confirme ausência de drift: `docker compose run --rm --no-deps migrate alembic check`.

Nunca edite uma migration já aplicada em outro ambiente; crie outra.

## Async (planejado, não implementado)

Não converta partes do código para `async` sem decisão explícita do usuário: chamar `Session` síncrona dentro de `async def` bloqueia o event loop. Uma migração para async exige engine/driver assíncronos (por exemplo `create_async_engine` + driver async), ajuste de `get_db`, testes e do `migrations/env.py`, e deve ser tratada como mudança estrutural (consulte `architecture-guard`).

## Antes de concluir

```bash
make test APP=backend                 # unitários (SQLite)
make -C apps/ressonant_backend lint   # ruff + format (escreve arquivos)
make -C apps/ressonant_backend check-structure
```

Para índices, paginação, N+1, locks e pooling, consulte `supabase-postgres-best-practices`; para revisão de segurança, `security-best-practices` (somente quando o usuário pedir). Para a receita passo a passo de um novo endpoint, leia [references/new-endpoint-recipe.md](references/new-endpoint-recipe.md).
