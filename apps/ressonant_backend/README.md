# Ressonant Backend

API FastAPI com **autenticação** (JWT) e **CRUD de usuários**. Rotas: `/docs` com o servidor no ar, ou a spec versionada em [`openapi.json`](openapi.json). Collection Postman em `../ressonant-api-collections` (fora do monorepo).

## Arquitetura

`routes → services → repository → models`, por módulo (`app/user`, `app/auth`). Erros via `common-errors`; logs via `common-logs`; telemetria via `common-telemetry` (o `CMD` do Docker usa `opentelemetry-instrument`; `make up` roda sem).

## Subir local

Da raiz do monorepo (detalhes no [README raiz](../../README.md)):

```bash
make setup               # cria .env (gera AUTH_SECRET) e instala deps
make infra-up            # Postgres compartilhado
make up APP=backend      # build, migrations e API em http://localhost:8000
make -C apps/ressonant_backend migrate/create-admin   # primeiro admin (ADMIN_* no .env)
```

Sem Docker para a API: com o Postgres no ar, `make migrate/apply up` aqui na pasta (usa o `DATABASE_URL` do `.env`).
`make help` lista os demais targets (`test`, `test-integration`, `lint`, `migrate/generate msg="..."`, `export-openapi`).

## Testes

- `make test`: unitários em SQLite, sem Docker.
- `API_BASE_URL=http://localhost:8000 make test-integration`: registro, login e persistência contra API e Postgres reais.
- `openapi.json` é a spec versionada; `make export-openapi` a atualiza e o teste `test_openapi_sync` falha se ela ficar velha.

## Configuração

Fonte de verdade: [`.env.example`](.env.example). `DATABASE_URL` e `AUTH_SECRET` (mín. 32 caracteres) são obrigatórios: o app não sobe sem eles e não há segredo padrão. No Docker o compose sobrescreve `DATABASE_URL` com o host `postgres`. Variáveis `OTEL_*` já apontam para o collector (ver [`GRAFANA.md`](../../GRAFANA.md)).

## Autenticação e permissões

- `POST /auth/register` é público e sempre cria usuário comum; `POST /auth/login` (e-mail + senha) devolve um access token de curta duração (30 min por padrão).
- Senhas com Argon2id. Login com falha devolve a mesma resposta para e-mail inexistente, senha errada e conta inativa.
- `/users` (listar, criar, status, deletar) é só para admin (`interno_adm`). `GET/PUT /users/{id}` aceita admin ou o próprio usuário.
- `DELETE` é soft delete (`status_ativo=false`); usuário inativo perde acesso mesmo com token já emitido.
- Primeiro admin: só pelo script `make migrate/create-admin`; nenhuma rota pública cria admin.

## Pendências conhecidas

Refresh token e rate limit de login (em loja externa, como Redis) ainda não existem.
