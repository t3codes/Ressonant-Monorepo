# AGENTS.md — Ressonant

Fonte **única e universal** de instruções para qualquer agente de IA neste monorepo (Claude Code, OpenCode, Codex, Gemini CLI, Hermes e outros). Padrões abertos: `AGENTS.md` e Agent Skills (`.agents/skills/<nome>/SKILL.md`, [agentskills.io](https://agentskills.io/specification)). Nenhuma regra mora em arquivo de fornecedor: o `CLAUDE.md` apenas importa este arquivo.

Legenda de estado usada abaixo: **Implementado** · **Parcial** · **Planejado** · **Não implementado**.

## 1. Produto

O Ressonant é o backend de uma plataforma de comunicação e colaboração em tempo real (categoria Slack), pensada para arquitetura moderna, baixa latência e escalabilidade, com agentes de IA e um RAG sobre um cofre Obsidian.

| Capacidade | Estado |
|---|---|
| Cadastro, login (JWT), perfil e CRUD de usuários, papel admin | **Implementado** (`apps/ressonant_backend`) |
| API FastAPI síncrona sobre PostgreSQL com migrations Alembic | **Implementado** |
| Telemetria (traces e métricas OTLP → Tempo/Prometheus → Grafana) | **Implementado** em dev local |
| Logs estruturados JSON com `trace_id` (stdout) | **Implementado**; exportação de logs via OTLP **não implementada** |
| Canais, threads, mensagens | **Planejado** (sem código) |
| Tempo real (WebSockets), Redis, mensageria, escalabilidade horizontal | **Planejado** (sem código, sem dependências) |
| Execução de fluxos por agentes de IA | **Planejado** |
| RAG conectado ao cofre Obsidian | **Planejado**; decisões de vector store, embeddings e sincronização **em aberto** |
| Refresh token, rate limit de login | **Não implementado** (pendências conhecidas) |
| Deploy (CI/CD de deploy, Kubernetes/Helm) | **Não implementado** (workflows de deploy foram removidos) |
| Collection Postman | **Implementado fora do monorepo** (`../ressonant-api-collections`, gerada do `openapi.json`) |

Princípios: correção e segurança primeiro; simplicidade antes de abstração; performance medida, não presumida; nunca descrever como existente o que está planejado.

## 2. Mapa do monorepo

```
apps/ressonant_backend/   API FastAPI (módulos app/auth, app/user; migrations/, tests/, openapi.json)
packages/                 libs sob o namespace common: errors, logs, telemetry (só deps), common-http, check-structure
infra/                    compose do Postgres e da observabilidade (OTel Collector, Tempo, Prometheus, Grafana)
docker-compose.yml        índice (include:) dos composes de infra/ e de cada app; não define serviços
hooks/                    políticas verificadas no pre-commit e em `make hooks`
docs/                     ADRs, guias (estrutura, testes, makefile), CI/CD, compose
templates/                molde de pyproject de lib e deploy-config
.agents/skills/           Agent Skills (ver §6)
GRAFANA.md                como iniciar e configurar o Grafana
```

Workspace uv na raiz (`apps/*`, `packages/*`), `uv.lock` na raiz, Python `==3.13.*`. Cada app builda, sobe e testa de forma independente.

## 3. Regras arquiteturais

Fontes: `docs/adrs/`, `docs/guides/`, `hooks/`, `packages/check-structure/README.md`, `packages/README.md`. Consulte-as em vez de duplicá-las; o essencial:

- **Backend (Implementado)**: `routes → services → repository → models`, por módulo. Rota sem regra de negócio; repository é o único a falar com a `Session`; o service decide commit/rollback; erros via `common.errors`, nunca `HTTPException` crua. Execução **síncrona** (`def` + psycopg2): não introduza `async` sem decisão explícita.
- **Contrato HTTP**: chaves **novas** em snake_case (ADR 0001); contrato já publicado não se converte nem se flagra. Mudou rota ou schema → atualize `openapi.json`.
- **Estrutura (check-structure)**: o guia `docs/guides/app-structure.md` descreve o formato **alvo** (`modules/<m>/{entrypoints,usecases,services,dataproviders}`); o backend usa outro layout, com bypasses declarados e 2 violações abertas (**Parcial**, migração em andamento). Código novo segue o layout do módulo vizinho; migrar para o alvo só com pedido explícito.
- **Hooks (Implementado)**: `requires-python = "==3.13.*"` em todo `pyproject.toml`; sem `__init__.py` em `packages/*/src/common/` (PEP 420).
- **Libs**: `packages/*` nunca importa `apps/*`; libs dependem de `opentelemetry-api`, nunca do SDK nem de `common-telemetry`. Código compartilhado nasce de uso real.
- **Telemetria em app Python**: dependa de `common-telemetry` (nenhum `opentelemetry-*` avulso); prefixe o entrypoint de produção com `opentelemetry-instrument`; `OTEL_SERVICE_NAME` único por processo; **não** escreva código de setup de telemetria; variáveis `OTEL_*` no `.env.example`.
- **ADRs**: `0001` vigente. `0002` (datas LME) descreve outro produto e **não se aplica**; a `0001` cita `ressonant-bff` e `ressonant-auth`, que não existem neste repo.
- **Segurança**: sem segredo em código ou em arquivo versionado; `AUTH_SECRET` e `DATABASE_URL` obrigatórios, sem default; senhas com Argon2id; SQL parametrizado; dados pessoais (CPF, telefone, e-mail) fora de logs.
- **Documentação** acompanha comportamento visível (uso, env vars, portas, targets, deploy). Não replica inventário: aponte para `make help`, `.env.example`, OpenAPI e ADRs. Comentário só explica o porquê. Descrição de PR: o que mudou, por quê e o que o revisor precisa olhar, legível em segundos.

## 4. Comandos (da raiz, salvo indicação)

Valem os targets reais do Makefile; veja `make help` e `make -C apps/ressonant_backend help`. `APP` aceita `backend` ou `ressonant_backend`.

| Tarefa | Comando |
|---|---|
| Preparar ambiente (`.env`, deps, pre-commit) | `make setup` |
| Subir Postgres | `make infra-up` · parar: `make infra-down` |
| Subir / parar / buildar / logs de um app | `make up APP=backend` · `make down APP=backend` · `make build APP=backend` · `make logs APP=backend` |
| Status dos containers | `make ps` |
| Observabilidade (Grafana em `http://localhost:3001`) | `make observability-up` · `make observability-down` |
| Migrations no Docker | `make migrate APP=backend` |
| Testes (app / tudo) | `make test APP=backend` · `make test` |
| Integração real (API no ar) | `API_BASE_URL=http://localhost:8000 make -C apps/ressonant_backend test-integration` |
| Lint e formatação sem escrever | `make lint-check` · `make format-check` |
| Lint + format com autofix | `make lint` |
| Tipos (mypy, só nos hooks) | `make typecheck` |
| Hooks de política | `make hooks` |
| Estrutura do backend | `make -C apps/ressonant_backend check-structure` |
| Isolamento de `packages/*` | `uv run check-structure --platform` |
| Gate completo | `make check` |
| Nova migration | `make -C apps/ressonant_backend migrate/generate msg="<descrição>"` |
| Aplicar migrations (local) | `make -C apps/ressonant_backend migrate/apply` |
| Criar o primeiro admin | `make -C apps/ressonant_backend migrate/create-admin` (`ADMIN_*` no `.env`) |
| Exportar OpenAPI | `make -C apps/ressonant_backend export-openapi` |
| API local com reload (sem telemetria) | `make -C apps/ressonant_backend up` |
| Alvos Docker do app | `make -C apps/ressonant_backend docker/up`, `docker/down`, `docker/build`, `docker/logs`, `docker/migrate` |

Nunca rode `docker compose down -v`, `docker volume rm` ou `prune`: os volumes guardam dados (o do Postgres é `ressonant_backend_pg-data`).

## 5. Princípios universais

1. **Inspecione antes de modificar**: leia o código vizinho, o ADR e a skill relevante.
2. **Não invente**: funcionalidade, comando, rota, arquivo ou resultado. Cite o que verificou e o que não conseguiu verificar.
3. **Respeite o escopo pedido**: valide se a mudança pertence à tarefa; sugira expansão, não a execute.
4. **Simplicidade**: sem wrapper que só repassa chamada, sem abstração prematura, sem flag/shim sem consumidor.
5. **Dependência nova** só com justificativa e `uv.lock` atualizado.
6. **Teste o que muda** e relate o resultado real do comando; nunca desative teste para passar.
7. **Nada de commit, push, rebase, reset, `--no-verify` ou histórico reescrito sem autorização explícita.** Antes de commitar, confirme escopo e mensagem. Mensagens em inglês, Conventional Commits (`tipo(escopo): descrição` em minúsculas, imperativo, até 72 caracteres); faça `git add` só de arquivos nomeados, nunca `git add -A`/`.`. Sem ok, deixe os arquivos sem stage.
8. **Não exponha segredos** (`.env`, tokens, senhas) em saída, logs, commits ou PRs.
9. **Ações destrutivas ou irreversíveis** (apagar dados, volumes, branches, recriar banco) exigem confirmação prévia.
10. **Revisão**: priorize risco real; sem nitpick; diferencie bloqueio de sugestão. Padrões vêm de práticas aceitas pelo time, não de comentário isolado nem de ferramenta automática sem validação.
11. **Idioma**: responda no idioma do usuário (PT-BR por padrão neste projeto); código, comandos, identificadores e mensagens de commit em inglês.

Referências antigas a `.claude/commands`, `.claude/rules` e `.claude/skills/local-code-review` **não existem mais** na árvore de trabalho (estão no histórico git); não as cite como disponíveis.

## 6. Skills e roteamento

**Antes de executar uma tarefa, consulte a(s) skill(s) da tabela.** Se a atividade envolve várias áreas, combine as skills correspondentes. Cada skill é `.agents/skills/<nome>/SKILL.md` (frontmatter `name` e `description`; recursos em `references/`, `scripts/`, `assets/`, carregados sob demanda). Se sua ferramenta não carrega skills sozinha, **leia o `SKILL.md` do caminho** indicado.

| Atividade | Skill obrigatória |
|---|---|
| Desenvolvimento Python/FastAPI, modelos, migrations, auth | `python-backend-specialist` |
| Revisão de código, "pronto para commit?" | `code-reviewer` |
| Docker, compose, CI/CD, OpenTelemetry, Grafana, diagnóstico de infra | `devops-observability` |
| Testes, cobertura, OpenAPI e contrato | `qa-and-openapi` |
| RAG, Obsidian, embeddings, busca, ingestão | `obsidian-rag-architect` |
| Mudança estrutural: nova app, nova lib, mover diretórios, check-structure, hooks, ADR | `architecture-guard` |

Combinações comuns: endpoint novo = `python-backend-specialist` + `qa-and-openapi`; nova app = `architecture-guard` + `python-backend-specialist` + `devops-observability`; revisão de PR de auth = `code-reviewer` + `security-best-practices`.

Skills complementares (instaladas; opcionais, nunca dependência do Ressonant):

| Skill | Use quando | Origem |
|---|---|---|
| `nvidia-skill-finder` | o pedido envolve produtos NVIDIA (NIM, NeMo Retriever, embeddings/rerankers NVIDIA, GPU). Consulta o catálogo ao vivo e **recomenda; não instale nada sem aprovação do usuário**. Preservada sem alterações (assinatura sigstore). | NVIDIA |
| `supabase-postgres-best-practices` | índices, N+1, paginação, pooling, locks, schema em Postgres (ignore o conteúdo específico de RLS/Supabase) | Supabase |
| `security-best-practices` | **somente** quando o usuário pedir revisão ou guia de segurança (referência FastAPI inclusive WebSocket) | OpenAI |
| `obsidian-markdown` | sintaxe Obsidian (wikilinks, embeds, callouts, properties) | kepano |
| `tempo` · `opentelemetry` | TraceQL e instrumentação OTel. Ignore passos de `git clone`, `docker compose up` e `pip install` dos exemplos (o Tempo já sobe pelo compose; o pacote do app é `common-telemetry`) | Grafana Labs |
| `python-observability` | logging estruturado, métricas e correlação em Python | wshobson |

As cópias externas são **sem modificação**, com commit fixado, licença e autoria em `ORIGIN.md` na própria pasta; não as edite. Trate-as como material de terceiros: não execute comandos que baixem código ou subam serviços sem confirmar com o usuário. Não há skill externa mantida para WebSockets, Redis/pub-sub, ingestão incremental de RAG ou Compose; use documentação oficial e as skills próprias.

Ao criar ou editar uma skill: padrão agentskills.io (`name` em kebab-case igual ao diretório, `description` ≤ 1024 caracteres, `SKILL.md` curto, detalhes em `references/`), sem campos específicos de fornecedor.

## 7. Compatibilidade entre ferramentas

Baseada na documentação oficial consultada em 2026-11-09; **não testada na prática** neste repositório. Não há configuração específica de ferramenta além do `CLAUDE.md`.

| Ferramenta | Instruções (`AGENTS.md`) | Skills em `.agents/skills/` | Observações |
|---|---|---|---|
| Claude Code | lê `CLAUDE.md`, que importa este arquivo via `@AGENTS.md` | **não lê** (só `.claude/skills/`) | Só `nvidia-skill-finder` tem symlink em `.claude/skills/`. As demais skills são alcançadas pelo roteamento do §6 (ler o `SKILL.md`) ou por symlinks adicionais, que exigem autorização |
| OpenCode | nativo (prioridade sobre `CLAUDE.md`) | lê | `@arquivo` não é importado; ID da skill vem do caminho |
| Codex CLI | nativo e hierárquico, limite de 32 KiB (este arquivo cabe) | lê | `agents/openai.yaml` é opcional (usado pela skill NVIDIA) |
| Gemini CLI | **exige** `context.fileName: ["AGENTS.md"]` no `settings.json` do usuário (ou `GEMINI.md` com `@AGENTS.md`) | lê | Doc consultada indica substituição pelo Antigravity CLI em 06/2026; status de skills não verificado |
| Hermes | nativo (um único tipo de contexto por sessão) | lê após `hermes skills trust` | Import `@` não comprovado |

Pontos não comprovados: import de arquivos no Codex e no Hermes, symlinks em OpenCode/Gemini/Hermes, formato exato de frontmatter no Gemini. Diferenças de interpretação do frontmatter e de carregamento de recursos auxiliares podem existir; em dúvida, mantenha o `SKILL.md` autossuficiente e leia `references/` explicitamente.
