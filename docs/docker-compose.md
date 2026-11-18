# Docker Compose

Como o monorepo orquestra containers localmente. Para o dia a dia use os targets `make` da raiz (`make help`).

## Modelo

- **Um compose por unidade**, agregados por `include:` no [`docker-compose.yml`](../docker-compose.yml) da raiz. A raiz não define serviços: é só um índice.
  - [`infra/docker-compose.yml`](../infra/docker-compose.yml): infra compartilhada (Postgres).
  - [`infra/observability/docker-compose.yml`](../infra/observability/docker-compose.yml): OTel Collector, Tempo, Prometheus e Grafana ([`GRAFANA.md`](../GRAFANA.md)).
  - `apps/<app>/docker-compose.yml`: serviços da app, ao lado do `Dockerfile` e do `.env`.
- Cada serviço builda e sobe sozinho. `docker compose up -d backend` sobe só o backend e o que ele declara em `depends_on` (Postgres e a migration); o resto não é tocado.
- Paths relativos em um compose incluído resolvem a partir da pasta dele.

## Redes

| Rede | Quem participa | Para quê |
| --- | --- | --- |
| `data` | Postgres e apps que usam banco | isola o banco de quem não precisa dele |
| `telemetry` | collector, Tempo, Prometheus, Grafana e apps instrumentadas | envio OTLP |

## Variáveis de ambiente

| Arquivo | Dono | Conteúdo |
| --- | --- | --- |
| `.env` (raiz) | infra | `POSTGRES_*`, portas, credenciais do Grafana |
| `apps/<app>/.env` | app | segredos e config da app (`AUTH_SECRET`, `OTEL_*`, `DATABASE_URL` para rodar fora do Docker) |

Os dois são criados por `make setup` a partir dos `.env.example` (fonte de verdade das chaves) e não são versionados. O `include:` da raiz passa os dois arquivos para a interpolação `${VAR}`; o `env_file:` do serviço injeta o `.env` da app no container.

## Convenções por app

- `build.context: ../..` (raiz) e `dockerfile: apps/<app>/Dockerfile`: o CI builda com o mesmo contexto.
- Migration como serviço one-shot (`migrate`) e `depends_on: condition: service_completed_successfully` no serviço principal.
- Portas publicadas em `127.0.0.1`.
- O serviço usa o nome curto da app (`apps/ressonant_<nome>` → serviço `<nome>`); é o que `APP=<nome>` resolve nos targets `make`.

## Adicionar uma app

1. Criar `apps/ressonant_<nome>/` com `Dockerfile`, `docker-compose.yml`, `.env.example` e `Makefile`.
2. Incluir o compose no `docker-compose.yml` da raiz com `env_file: [.env, apps/ressonant_<nome>/.env]`.
3. Liberar `!apps/ressonant_<nome>/**` no [`.dockerignore`](../.dockerignore).
4. Se for Python, manter `package = false` no `pyproject.toml`: o Dockerfile do backend leva só o manifest das apps irmãs para o `uv.lock` fechar.

## Volumes e dados

`make down` e `make infra-down` não removem volumes. O volume do Postgres chama-se `ressonant_backend_pg-data` (nome legado preservado de propósito, já guarda dados). Apagar dados é sempre um passo manual (`docker volume rm`).
