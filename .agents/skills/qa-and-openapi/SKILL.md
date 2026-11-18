---
name: qa-and-openapi
description: Qualidade, testes e contrato OpenAPI do Ressonant. Use ao escrever ou corrigir testes (pytest unitários em SQLite, testes de integração contra API e Postgres reais), rodar lint, formatação, mypy ou check-structure, medir cobertura, validar rotas, ou ao sincronizar openapi.json (scripts/export_openapi.py e test_openapi_sync) depois de mudar rotas ou schemas.
metadata:
  scope: tests-and-contract
  language: pt-BR
---

# qa-and-openapi

Use os **comandos reais** abaixo. Não invente targets.

## Comandos

| Objetivo | Comando |
|---|---|
| Testes de um app | `make test APP=backend` |
| Testes de tudo (libs + apps) | `make test` |
| Integração real (API e Postgres no ar) | `API_BASE_URL=http://localhost:8000 make -C apps/ressonant_backend test-integration` |
| Lint sem escrever | `make lint-check` |
| Formatação sem escrever | `make format-check` |
| Lint + format com autofix | `make lint` (raiz) ou `make -C apps/ressonant_backend lint` |
| Tipos (mypy; só os hooks) | `make typecheck` |
| Estrutura | `make -C apps/ressonant_backend check-structure` e, na raiz, `uv run check-structure --platform` |
| Hooks de política | `make hooks` |
| Gate completo | `make check` (lint-check, format-check, typecheck, test, hooks) |
| Exportar OpenAPI | `make -C apps/ressonant_backend export-openapi` |
| Rodar um teste | `cd apps/ressonant_backend && uv run pytest tests/test_auth.py -k login` |

A cobertura (`pytest-cov`) está instalada no grupo dev, mas **não há meta nem alvo configurado**: rode `uv run pytest --cov=app tests` só se o usuário pedir.

## Suítes existentes

- **Unitários** (`apps/ressonant_backend/tests/`, 22 testes): `test_auth.py`, `test_users.py`, `test_settings.py`. `conftest.py` fixa `DATABASE_URL=sqlite://` e `AUTH_SECRET` antes de importar o app, usa SQLite em memória com `StaticPool`, sobrescreve `get_db` por `dependency_overrides` e oferece `client`, `session_factory`, `make_user`, `login`, `admin_headers`, `register_payload`, `VALID_CPFS`.
- **Contrato**: `test_openapi_sync.py` compara o `openapi.json` versionado (em `apps/ressonant_backend/openapi.json`) com `app.openapi()`.
- **Integração real** (`tests/integration/test_live_api.py`, 5 testes): sem mocks, contra API e Postgres; **pulada** sem `API_BASE_URL`. Cria e-mail/CPF únicos por execução (os dados ficam no banco de dev).
- Libs: `packages/*/tests` (common-http, errors, logs). `check-structure` e `telemetry` não têm testes.

Não existem: testes de carga, testes de cobertura de migração, testes de WebSocket, collection no CI. A collection Postman vive **fora** do monorepo (`../ressonant-api-collections`, gerada do `openapi.json`).

## Divergência a conhecer

`docs/guides/unit-tests.md` manda mockar tudo que sai do processo e organizar em classes `Test<Alvo>`; os testes do backend usam SQLite real em memória e funções simples. Siga o estilo do arquivo vizinho; não reescreva testes existentes para o guia sem pedido.

## OpenAPI: fluxo

1. Mudou rota, método, schema ou resposta → `make -C apps/ressonant_backend export-openapi` (usa `scripts/export_openapi.py`, que define `DATABASE_URL=sqlite://` e um `AUTH_SECRET` fictício e **não** precisa de banco).
2. Revise o diff do `openapi.json` (só deve conter o que você mudou).
3. `make test APP=backend` (o `test_openapi_sync` precisa passar).
4. A collection Postman fora do repo é regenerada com `python3 scripts/build_collection.py` na pasta dela; ela falha se uma rota ficar sem request.

## Como escrever um teste novo

- Reuse as fixtures; um cenário por teste; nomes descritivos (`test_<comportamento>`).
- Para cada endpoint novo cubra: 2xx, 401 (sem token), 403 (sem permissão), 404, 409 e 422 quando aplicável. Nenhum teste dorme ou depende de ordem.
- Bug corrigido → teste de regressão que falha sem a correção.
- Nunca desative, pule ou afrouxe teste para "passar". Se falhar, investigue a causa.
- Valide contra o real quando a dúvida for de integração (Postgres, migration, Docker): `make up APP=backend` e a suíte de integração; mocks não provam isso.
- Dado pessoal em teste: use valores fictícios (CPFs válidos de teste já em `VALID_CPFS`).

## Ao relatar

Informe o comando e o resultado reais (ex.: "22 passed, 5 skipped"); distinga o que rodou do que não rodou. Para checklist de segurança de API (authz, mass assignment, validação), a skill externa `security-best-practices` complementa, apenas quando o usuário pedir.
