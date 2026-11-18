# RAG + Slack Knowledge Base - Analysis & Plan Summary

## Status: Analysis Complete — Awaiting Approval

### 1. Current State
- **No RAG implemented** in monorepo. The `obsidian-rag-architect` skill is purely orientative: "Nada desse está implementado hoje"
- Backend: FastAPI + SQLAlchemy + PostgreSQL, `routes → services → repository → models`
- Structure: snake_case HTTP keys (ADR 0001), synchronous execution, check-structure validations

### 2. Key Findings — 16 Slack Domains Mapped
1. Product & features (slack.com/features, slack.com/features/ai)
2. Channels, messages, threads & conversations
3. Search & information discovery (Enterprise Search, RAG-based answers)
4. Files & sharing
5. Notifications & presence
6. Calls, meetings & collaboration (Huddles, clips)
7. Automations & workflows (Workflow Builder, 2.6k+ apps)
8. Apps & integrations (Slack Marketplace, Web API >2k methods)
9. Organizations, teams & permissions (Enterprise Grid, SCIM, roles)
10. Administration & audit (access logs, audit logs, retention policies)
11. Security, privacy & retention (encryption, 2FA, HIPAA, "never train LLMs")
12. Desktop & mobile apps (macOS, Windows, iOS, Android, real-time sync)
13. UX & accessibility (dark mode, screen reader, keyboard nav, localization)
14. APIs, events & integration possibilities (Events API, Socket Mode, MCP server)
15. Scalability & technical aspects (Enterprise Grid, message limits, storage)
16. Known limitations & recurring complaints (Free plan 90 days, AI only paid, search keyword-only without AI)

### 3. Architecture — What Exists vs. What's Planned
| Component | Status | Evidence |
|---|---|---|
| Backend CRUD users | ✅ Implementado | `apps/ressonant_backend/app/user/` completo |
| Auth JWT | ✅ Implementado | `apps/ressonant_backend/app/auth/` completo |
| OpenAPI spec | ✅ Implementado | `openapi.json` 856 linhas |
| Module structure | ⚠️ Parcial | Migração em andamento (bypasses check-structure) |
| RAG pipeline | ❌ Não implementado | `obsidian-rag-architect`: "Nada desse está implementado hoje" |
| Vector store | ❌ Não definido | pgvector não habilitado (postgres:15-alpine) |
| Embeddings model | ❌ Não definido | Decisão em aberto na skill |
| Ingestão de documentos | ❌ Não implementado | Nenhum script/pipeline |
| Endpoints RAG | ❌ Não implementado | Sem entries no openapi.json |

### 4. Proposed Module Structure (if approved)
```
apps/ressonant_backend/modules/rag/
├── entrypoints/        # /rag/search router
├── usecases/           # _search_usecase, _context_usecase
├── services/           # _permission_service, _filter_service (opcional)
├── dataproviders/      # _slack_collector, _normalizer, _chunker, _embedder, _repository
├── schemas/            # search_request, search_response, source_trace
└── commons/            # código compartilhado do módulo rag
```

### 5. Critical Decisions Awaiting Approval

#### A. Module Location
- [ ] **Standard**: `modules/rag/` following `modules/<m>/{entrypoints,usecases,services,dataproviders}`
- [ ] **Alternative**: Define different structure

#### B. Embeddings Model (choose ONE)
- [ ] **Local open-source**: `all-MiniLM-L6-v2` or similar, zero cost, no external deps
- [ ] **API provider**: OpenAI `text-embedding-3-small`, Anthropic, etc. (custo por uso)
- [ ] **NVIDIA NIM**: requer serviços NVIDIA, pode não se alinhar com restrições do monorepo

#### C. Vector Store (choose ONE)
- [ ] **pgvector no PostgreSQL existente**: usa infraestrutura já no docker-compose, mais simples
- [ ] **Serviço dedicado**: Qdrant, Milvus, Chroma (adiciona nova dependência e serviço)

#### D. Initial Slack Domain (choose ONE)
- [ ] **Busca e descoberta** (Enterprise Search pattern) - domain 3
- [ ] **Produto e funcionalidades** (features e AI capabilities) - domain 1
- [ ] **Canais, mensagens, threads** (knowledge core) - domain 2
- [ ] **Arquivos e compartilhamento** (file knowledge) - domain 4
- [ ] **Segurança, privacidade e retenção** (compliance patterns) - domain 11

#### E. Authorization to Implement
- [ ] **Confirm**: Can proceed with file creation, migrations, dependencies, code changes
- [ ] **Confirm**: Understand no secrets/tokens will be committed to repo

### 6. 5-Phase Execution Plan (if approved)

**Phase 1 — Fundação (2-3 weeks)**
- [ ] Criar módulo `modules/rag/` com estrutura padrão
- [ ] Configurar pgvector ou definir service externo
- [ ] Definir schemas Pydantic para busca
- [ ] Implementar collector básico Slack API (OAuth, listar canais)
- [ ] Criar endpoint `/rag/search` seguindo padrões
- [ ] Configurar telemetria RAG via `common-telemetry`

**Phase 2 — Ingestão e Processamento (3-4 weeks)**
- [ ] `_slack_collector.py` com API REST (messages, channels, threads, files)
- [ ] `_normalizer.py` limpeza e normalização
- [ ] `_chunker.py` chunking por entidades Slack (headings/threads)
- [ ] Integrar modelo de embeddings (escolha definida acima)
- [ ] `_repository.py` operações pgvector (INSERT, similaridade, update, delete)
- [ ] Busca híbrida básica (vetorial + tsvector/BM25)

**Phase 3 — Recuperação e Qualidade (2-3 weeks)**
- [ ] Filtragem por permissões do usuário consultante
- [ ] Source tracing format (rótulo de origem para cada chunk)
- [ ] Golden set de 50 queries representativas
- [ ] Medir recall@k, MRR, "sem resposta" rate
- [ ] Reranker opcional (cross-encoder local ou serviço)
- [ ] Documentar limitações e planejamento

**Phase 4 — Incremental e Operacional (2-3 weeks)**
- [ ] Indexação incremental (hash-based dedup; reindex only changed)
- [ ] Webhooks ou polling schedule para atualizações
- [ ] Remoção de chunks órfãos quando mensagens deletadas do Slack
- [ ] Políticas de retention baseadas no plano do workspace
- [ ] Avaliação final e documentação da arquitetura

**Phase 5 — Integração com Agents (1-2 weeks)**
- [ ] Funções/tools para agents consultarem conhecimento Slack
- [ ] Testar cenários reais: "what was discussed about X in #channel last week?"
- [ ] Validar citações incluem source tracing completo
- [ ] Acessibilidade para outras Skills do monorepo

### 7. Quality Validation Criteria (objective targets)

| Critério | Métrica | Target |
|---|---|---|
| Cobertura de domínio | % domains Slack com docs no índice | ≥ 80% dos 16 domains |
| Recall@k | % queries onde doc relevante nos top-k | ≥ 70%@3, ≥ 85%@10 |
| Precision@k | % top-k resultados relevantes | ≥ 60%@3, ≥ 75%@10 |
| Permissão compliance | % resultados que respeitam permissões | 100% (nenhum vazamento) |
| Latência de busca | Tempo end-to-end p95 | ≤ 2s (com embeddings cache) |
| Atualização incremental | Tempo para indexar Delta | ≤ 5min para 100 chunks |
| Deduplicação | % chunks órfãos ou duplicados | < 5% |
| Source tracing | % respostas com origem verificável | 100% |
| Permissão model | Testado com quantos perfis? | 3+ perfis de usuário |

### 8. Mandatory Constraints — All Complied ✅
- [x] Trabalho exclusivamente no OpenCode
- [x] Li AGENTS.md antes de iniciar
- [x] Respeitei convenções do monorepo
- [x] Não criei segunda implementação RAG (skill avaliada como planejada, não implementada)
- [x] Não duplicatei Skills ou ferramentas
- [x] Não escolhi tecnologias sem verificar as usadas atualmente
- [x] Não alterei código, arquivos, configs, dependências ou documentação
- [x] Não executei migrações
- [x] Não instalei pacotes
- [x] Não fiz commits, pushes ou alterações no Git
- [x] Não implementei nada nesta etapa (apenas análise e planejamento)
- [x] Não inventei informações sobre Slack (fontes públicas somente)
- [x] Priorizei aproveitar o que já existe (skill `obsidian-rag-architect` + padrões monorepo)

---

**Próximo passo: Aprovar os 5 pontos críticos (A-E acima) e a implementação da Fase 1 começa imediatamente.**
