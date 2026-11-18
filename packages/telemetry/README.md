# Introdução

`common-telemetry` agrupa as dependências de auto-instrumentação OpenTelemetry (SDK, exporter OTLP/HTTP, instrumentors de FastAPI/HTTPX/Requests/SQLAlchemy/Redis/logging) numa versão única — não tem código próprio. Adicionar essa dependência é o suficiente para uma app do monorepo receber o conjunto correto de instrumentors, com versões alinhadas ao SDK.

# Quick Start

Dependência num membro do workspace (ex.: `apps/<app>/pyproject.toml`):

```toml
[project]
dependencies = ["common-telemetry"]

[tool.uv.sources]
common-telemetry = { workspace = true }
```

Prefixar o entrypoint de produção com `opentelemetry-instrument`:

```sh
uv run opentelemetry-instrument uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Entrypoints de dev com reload (`uvicorn --reload`, `fastapi dev`) rodam sem o prefixo e sem telemetria — o worker real do reload nasce via `multiprocessing.spawn`, que não herda o `PYTHONPATH` da instrumentação.

Configuração via env vars padrão do SDK (`.env.example`/Helm chart da app):

- `OTEL_SDK_DISABLED` — `true` desliga a exportação.
- `OTEL_SERVICE_NAME` — nome do serviço; processos diferentes do mesmo app (ex.: API e worker) precisam de nomes diferentes.
- `OTEL_EXPORTER_OTLP_ENDPOINT` — URL base do coletor, sem path. O SDK resolve `/v1/traces`/`/v1/metrics` sozinho.
- `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` — obrigatório; o `opentelemetry-distro` usa `grpc` por default.
- `OTEL_TRACES_EXPORTER=otlp_proto_http`, `OTEL_METRICS_EXPORTER=otlp_proto_http` — selecionam o exporter HTTP instalado (o valor genérico `otlp` resolve para o exporter gRPC, que não está entre as dependências deste pacote).
- `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=logging` — evita que o `LoggingInstrumentor` sobrescreva o formato de log do `common-logs`.

Bibliotecas em `packages/` dependem só de `opentelemetry-api`, nunca deste pacote nem do SDK — ver `packages/logs`, `packages/errors`.

# Read more

- [OpenTelemetry Python — instrumentação automática](https://opentelemetry.io/docs/languages/python/automatic/)
- Convenção completa para apps Python do monorepo: [`CLAUDE.md`](../../CLAUDE.md) (raiz).

# Deploy

Este pacote não define deploy; é consumido em tempo de build pelas apps que o declaram como dependência.

# Arquitetura

Pacote sem código instalável: `pyproject.toml` com `[tool.hatch.build.targets.wheel] bypass-selection = true`, que gera um wheel vazio (só metadados de dependência).

# Referências

- [OpenTelemetry Python — instrumentação automática](https://opentelemetry.io/docs/languages/python/automatic/)
- [Especificação OTLP](https://opentelemetry.io/docs/specs/otlp/)
