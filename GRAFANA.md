# Grafana: iniciar e configurar

Observabilidade local do monorepo. O Grafana sobe já provisionado (datasources e dashboard), sem configuração manual.

```
app (opentelemetry-instrument) ──OTLP/HTTP──▶ otel-collector ──▶ Tempo (traces)
                                                     └────────▶ Prometheus (métricas) ◀── Grafana ──▶ Tempo
```

| Serviço | Porta no host | Uso |
| --- | --- | --- |
| Grafana | `http://localhost:3001` | UI |
| Prometheus | `http://localhost:9090` | consulta de métricas |
| OTel Collector | `http://localhost:4318` | recebe OTLP/HTTP (Tempo não é exposto) |

Todas as portas escutam só em `127.0.0.1`.

## Credenciais (somente dev local)

| Campo | Valor padrão | Onde muda |
| --- | --- | --- |
| Usuário | `admin` | `GRAFANA_ADMIN_USER` no `.env` da raiz |
| Senha | `ressonant-dev` | `GRAFANA_ADMIN_PASSWORD` no `.env` da raiz |
| Porta | `3001` | `GRAFANA_PORT` no `.env` da raiz |

Usuário e senha só valem na **primeira** criação do volume `grafana-data`. Para trocar depois:
`docker compose exec grafana grafana cli admin reset-admin-password <nova>`.
Não use esses valores fora do ambiente local.

## Iniciar

Pré-requisitos: Docker + Docker Compose v2, `make`.

```bash
make setup               # cria .env (raiz) e apps/*/.env; não sobrescreve os existentes
make observability-up    # sobe collector, Tempo, Prometheus e Grafana e espera ficarem saudáveis
make up APP=backend      # opcional agora, mas é o backend que gera telemetria
```

Abra <http://localhost:3001>, entre com as credenciais acima e vá em **Dashboards → Ressonant → Ressonant Backend**.

Parar (volumes preservados): `make observability-down`. Logs: `docker compose logs -f grafana`.

## O que já vem provisionado

Arquivos em [`infra/observability/grafana/`](infra/observability/grafana):

| Item | Arquivo | Conteúdo |
| --- | --- | --- |
| Datasources | `provisioning/datasources/datasources.yaml` | `Prometheus` (padrão, uid `prometheus`) e `Tempo` (uid `tempo`) |
| Provider de dashboards | `provisioning/dashboards/dashboards.yaml` | carrega `dashboards/*.json` na pasta **Ressonant** |
| Dashboard | `dashboards/ressonant-backend.json` | req/s por rota, p95, status HTTP, taxa 5xx, requisições ativas, pool do banco, traces recentes |

O Grafana relê os arquivos a cada ~30 s. Dashboards provisionados não podem ser salvos pela UI
(`disableDeletion`): edite o JSON no repositório. Para criar um novo, monte-o na UI, exporte
(**Share → Export → Save to file**) e salve em `dashboards/`.

## Verificar que a telemetria chega

1. Gere tráfego: `curl localhost:8000/health/ready` algumas vezes (ou use a collection Postman).
2. Espere ~15 s (as métricas exportam a cada 10 s).
3. No dashboard, os painéis de requisições devem mostrar dados.
4. Em **Explore → Tempo**, a query `{ resource.service.name = "ressonant_backend" }` lista traces.

Pela linha de comando:

```bash
# alvo do Prometheus saudável
curl -s localhost:9090/api/v1/targets | grep -o '"health":"[a-z]*"'
# métricas do backend
curl -s 'localhost:9090/api/v1/query?query=http_server_duration_milliseconds_count' | head -c 300
# login e datasources no Grafana
curl -s -u admin:ressonant-dev localhost:3001/api/datasources
```

## Configurar uma nova app

1. No `.env` da app, aponte para o collector e dê um nome próprio ao processo (modelo em
   [`apps/ressonant_backend/.env.example`](apps/ressonant_backend/.env.example)):
   `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`,
   `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_TRACES_EXPORTER=otlp_proto_http`,
   `OTEL_METRICS_EXPORTER=otlp_proto_http`.
2. No compose da app, ligue o serviço à rede `telemetry`.
3. Inicie o processo com o prefixo `opentelemetry-instrument` (ver `CLAUDE.md`, convenção OpenTelemetry).
4. Filtre por `service_name="<OTEL_SERVICE_NAME>"` nas queries.

Fora do Docker, aponte `OTEL_EXPORTER_OTLP_ENDPOINT` para `http://localhost:4318`.

## Troubleshooting

| Sintoma | Causa provável e correção |
| --- | --- |
| `defina GRAFANA_ADMIN_PASSWORD no .env` | falta o `.env`; rode `make setup` |
| Login falha com a senha do `.env` | o volume já existia com outra senha; use `reset-admin-password` (acima) |
| Porta 3001 em uso | mude `GRAFANA_PORT` no `.env` e rode `make observability-up` |
| Painéis vazios | sem tráfego nos últimos minutos ou backend fora do ar (`make up APP=backend`); ajuste o intervalo de tempo |
| Prometheus sem `service_name` | app sem `opentelemetry-instrument` ou sem as variáveis `OTEL_*` acima: confira com `docker compose logs backend` |
| Traces ausentes, métricas ok | confira `docker compose logs otel-collector tempo` |
| Datasource "Tempo" mostra erro de health | o teste de health do plugin não é suportado no Grafana 11.1; valide pelo Explore |
| Resetar todo o histórico | `docker compose down` + remover os volumes `*_grafana-data`, `*_prometheus-data`, `*_tempo-data` (apaga só observabilidade; o Postgres não é afetado) |
