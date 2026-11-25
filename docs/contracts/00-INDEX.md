# Catálogo de Contratos de API — mocks do frontend; status revisitado no backend

- Extraído por 6 lotes de @frontend-react (modelos free OpenCode), em 2026-11-18.
- **Regra original**: 100% evidência dos arquivos do frontend (`ressonant-frontend-work`). Zero invenção de rotas/campos.
- **Escopo**: contratos tal como o frontend os consome (`src/repositories/contracts.ts` + `src/mocks/*.json` + `src/services/*`).
- **Legenda de estado**: **Entregue — Fase 0** · **Implementado** · **Planejado — Fase N (gate)**. "Implementado"/"Entregue" descrevem o backend; o consumo pelo frontend é dito explicitamente quando verificado.
- **Status frente ao backend — atualizado em 2026-11-21 (Fase 0, O0–O4; gates P0-4/P0-5/P0-6)**: conferido contra `apps/ressonant_backend/openapi.json` (66 paths, SHA `da24e1aad76ef52bc078a203f797ef96e4165330b703f17cec1ad475b7c16869`) e `app/main.py`. **Implementado** significa que a rota existe no backend; **não** significa, por si só, que o frontend a consome. D1 e D7 estão **Entregues — Fase 0** e o frontend já consome `GET /me/context`; o mapeamento camelCase ↔ snake_case vive nos adaptadores HTTP do frontend e o backend deriva o usuário do JWT.

## Índice por domínio

| # | Domínio | Arquivo | Operações | Auth no mock | Status frente ao backend |
|---|---------|---------|-----------|--------------|--------------------------|
| 1 | Identity / Workspace / Auth | [01-identity-workspace-auth.md](01-identity-workspace-auth.md) | 29 | Mock: sem token; HTTP: Bearer (authApi existente) | **Implementado**: `/auth/register`, `/login`, `/logout`, `/me` e CRUD `/users`; `GET /me/context` **Entregue — Fase 0** (D7; shape resumido abaixo) |
| 2 | Chat (channels/conversations/messages) | [02-chat-channels-messages.md](02-chat-channels-messages.md) | 26 | `userId` explícito, sem sessão | **Implementado**: `/channels`, `/conversations`, `/messages` e WebSocket `/ws/{room_kind}/{room_id}`; `userId` do JWT e paridade de campos pendentes no frontend |
| 3 | Reactions / Read-states / Notifications | [03-reactions-readstates-notifications.md](03-reactions-readstates-notifications.md) | 9 | `userId` explícito, sem sessão | **Implementado**: `/reactions`, `/read-states`, `/notifications` |
| 4 | Mail | [04-mail.md](04-mail.md) | 11 | `userId` explícito, sem sessão | **Implementado**: `/mail` (criar, listar, detalhar, marcar lido, editar) |
| 5 | Kanban boards/teams/columns | [05-kanban-boards-teams.md](05-kanban-boards-teams.md) | 2 | Cookie de sessão no adapter HTTP | **Implementado**: `/boards`, `/boards/{id}/columns` e `/teams`; segregação e regras de fluxo são **Planejado — Fase 2** |
| 6 | Kanban cards | [06-kanban-cards.md](06-kanban-cards.md) | 4 | Cookie de sessão no adapter HTTP | **Implementado**: `/cards` (criar, listar, detalhar, atualizar, clonar, `move`, `block`, `unblock`); `CardResponse.key` e `GET /cards/{id}/history` são **Planejado — Fase 2 (P2-2/P2-4)** |
| 7 | Hierarquia, bootstrap e billing (fora dos mocks) | [matriz de atores](../../apps/ressonant_backend/docs/management-actor-action-matrix.md) | 4 de billing + `/me/context` + 8 de gestão | Bearer (JWT) | **Entregue — Fase 0** (P0-4/P0-6): tabelas organizacionais e de billing, RBAC de cinco eixos, `audit_events` append-only; ver §"Entregue — Fase 0" |

**Total: 81 operações catalogadas** (snapshot do frontend; não é contagem de rotas do backend).

## Achados transversais (obrigatórios para o backend)

1. **Identidade via JWT apenas.** Em todos os mocks o `userId` chega como parâmetro explícito. No backend, todo ID de usuário deve ser extraído do token JWT — **nunca** por URL/body. `contracts.ts` já prevê: "A real server derives the user from the session".
2. **Paridade de formatos.** Frontend: camelCase + ids prefixados (`user_*`, `ch_*`, `msg_*`, `card_*`, `board_*`, `team_*`). Backend: snake_case + UUID. Mapeamento precisa ser formalizado (relatório de paridade do @dba-postgres).
3. **Ausências globais nos mocks**: paginação, ordenação, filtros server-side (tudo client-side), escopo de auth no realtime.
4. **Operações opcionais até o backend existir**: `createCard`, `cloneCard`, `NotificationRepository.create` (mock implementa; HTTP ausente).
5. **Mail diverge do protótipo Python** `backend/mock_data.py` (snake_case, `is_read: Dict`, pasta `inbox`/`sent`) — ver seção 2 de `04-mail.md`.
6. **Shape User HTTP**: `UserResponse` do backend (confirmado em 2026-11-21) traz `id`, `email`, `cpf`, `telefone`, `idade`, `termos_contrato`, `status_ativo`, `interno_adm`, `name`/`title` (aditivos, migration `0015`; testados em `tests/test_context.py`), campos de avatar e datas — **não** traz `handle`/`color`/`presence`/`workspaceIds` (o adapter preenche defaults; os workspaces vêm de `workspaces[]` no `/me/context`). Quebra de paridade a resolver.
7. **Tipo misto**: `readAt` vem número/ISO/null nos mocks vs `ISODate | null` no TS.
8. **Gestão e billing fora do catálogo**: as oito operações reais `/workspaces/{workspace_id}/management/*`, as quatro de `/organizations/{organization_id}/billing*` e `GET /me/context` não vieram dos mocks; estão documentadas na [matriz de atores](../../apps/ressonant_backend/docs/management-actor-action-matrix.md) e no `openapi.json`.

## Decisões aprovadas — Fase 0, O0

| ID | Decisão aprovada | Estado no monorepo |
|---|---|---|
| **D1** | Configuração: `VITE_API_BASE_URL` como única variável de **URL** (default `/api`, proxy com `rewrite`) e `VITE_DATA_MODE=mock\|http` como **flag de modo** (default `http`); remover as outras sete variáveis | **Entregue — Fase 0 (O4, P0-2/P0-6)**: decisão fechada e já consumida pelo frontend (`src/repositories/index.ts`); nenhuma `VITE_*` é lida pelo backend |
| **D7** | Bootstrap: adotar `GET /me/context` como canônico; manter `GET /auth/me`; **não** criar `/auth/bootstrap` | **Entregue — Fase 0 (O4b, P0-3/P0-6)**: `/me/context` implementado e consumido uma vez por sessão no frontend; `/auth/me` mantido por compatibilidade; `/auth/bootstrap` não será criado |

Fonte das decisões: [Plano Mestre Unificado, §9](../../../docs/PLANO_MESTRE_UNIFICADO.md) (fora do monorepo).

## Entregue — Fase 0 (O1–O4; gates P0-4/P0-5/P0-6)

- **`GET /me/context` (D7, P0-3/P0-6)**: bootstrap canônico autenticado, sem query parameters, em `app/modules/context/`. Shape resumido: `user` (`UserResponse`), `organizations[]` (`id`, `name`, `slug`, `role`, `status`), `active_organization`, `workspaces[]` (`id`, `name`, `slug`, `organization_id`, `role`, `member_ids`, `teams[]` com `key_prefix`, `capabilities`, `permission_version`), `capabilities` (`management` com 14 flags, `billing.view/manage`, `domain.cards_write`), `subscription` (`plan_code`, `plan_name`, `status`, `seats_purchased`, `seat_limit`, `trial_ends_at`, `current_period_end`, `price_cents`, `overage_cents_per_seat`, `provider=stub`) e `permission_version`. `GET /auth/me` permanece por compatibilidade; `/auth/bootstrap` está fora de escopo por D7.
- **Tabelas entregues**: `organizations`, `organization_members` (`owner|admin|member|billing_owner`, `active|inactive`, no máximo um `owner` ativo por organização) e `invitations` (migration `0015`, com backfill 1:1 de `workspaces.organization_id`, `teams.key_prefix` e `cards.key`); `plans` (catálogo `inicial`/`equipe`/`empresa`) e `subscriptions` (migration `0016`, seats/trial/uplift, no máximo uma assinatura ativa por organização).
- **Papéis de cinco eixos** (matriz §6 do Plano Mestre; regras R9/R10): Dono da Empresa (`organization_members.role=owner`) vê/altera billing e concede grants até `grant`; Billing Owner vê/altera billing e não concede grants nem `modify` (separação de poderes); Admin da org e Dono/Admin de workspace concedem até `modify`, nunca `grant` (R9); o titular de `grant` também não escala a `grant`, embora possa conceder até `modify`; `interno_adm` fora de membership exige `reason` com evento `break_glass` (R10); viewer sem vínculo tem deep-link negado com `404` (D5 — na API, `403`/`404` indistinguíveis para não enumerar). Detalhes na [matriz de atores](../../apps/ressonant_backend/docs/management-actor-action-matrix.md).
- **Billing (P0-4)**: `GET`/`PATCH /organizations/{organization_id}/billing`, `POST /organizations/{organization_id}/billing/subscription` e `PATCH /organizations/{organization_id}/billing/subscription/status`. Respostas com `provider=stub` e `simulation=true`: gateway local, sem rede, sem chave e sem cobrança real; preços são proposta de planejamento (D3). Ciclo `trialing→active→past_due→canceled` e `SEAT_LIMIT_EXCEEDED` validado antes do commit.
- **Auditoria (O3, P0-5)**: `audit_events` generalizado (`organization_id`, `scope`, `actor_role`, `permission_version`, `request_id`, `result`) e append-only no Postgres por `REVOKE UPDATE, DELETE` ao papel da aplicação + trigger `audit_events_append_only` (migration `0017`). Mutação de domínio registra evento no mesmo commit, com redação de campos sensíveis.
- **D1 e D7**: D1 (config, P0-2/P0-6) fechado e consumido no frontend — apenas `VITE_API_BASE_URL` e `VITE_DATA_MODE`; D7 (bootstrap, P0-3/P0-6) entregue no backend e no frontend, sem `/auth/bootstrap`.

## Planejado — fases seguintes (fora do O0)

- Cadastro atômico (`POST /auth/register` evoluído) e convites por e-mail/aceite de token — **Planejado — Fase 1 (P1-3/P1-5)**; a tabela `invitations` já existe, mas ainda não há endpoints de convite.
- Exposição/geração concorrente de chaves legíveis de card (`CardResponse.key`, `team_card_sequences`) e regras WIP persistidas — **Planejado — Fase 2 (P2-2/P2-5)**; o backfill de `cards.key` e `teams.key_prefix` veio na `0015`.
- Segregação de boards/cards por vínculo com deep-link `404` na UI e `GET /cards/{id}/history` — **Planejado — Fase 2 (P2-1/P2-4)**.
- Vínculo Chat↔card e remoção de seeds do caminho HTTP — **Planejado — Fase 4 (P4-1/P4-2)**.

## Fora do escopo desta missão (O0)

- Inventário do legado × catálogo (`07-legacy-inventory.md`), parecer de cybersecurity e desenvolvimento rota por rota pertencem às fases seguintes do Plano Mestre Unificado (documento não versionado neste repositório), não ao saneamento documental O0.
