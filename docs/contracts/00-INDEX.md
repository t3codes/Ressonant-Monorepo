# Catálogo de Contratos de API — mocks do frontend; status revisitado no backend

- Extraído por 6 lotes de @frontend-react (modelos free OpenCode), em 2026-11-18.
- **Regra original**: 100% evidência dos arquivos do frontend (`ressonant-frontend-work`). Zero invenção de rotas/campos.
- **Escopo**: contratos tal como o frontend os consome (`src/repositories/contracts.ts` + `src/mocks/*.json` + `src/services/*`).
- **Status frente ao backend — atualizado em 2026-11-21 (Fase 0, O0)**: conferido contra `apps/ressonant_backend/openapi.json` e `app/main.py`. **Implementado** significa que a rota existe no backend; **não** significa que o frontend a consome. O mapeamento camelCase ↔ snake_case e a derivação do `userId` do JWT permanecem pendências do frontend.

## Índice por domínio

| # | Domínio | Arquivo | Operações | Auth no mock | Status frente ao backend |
|---|---------|---------|-----------|--------------|--------------------------|
| 1 | Identity / Workspace / Auth | [01-identity-workspace-auth.md](01-identity-workspace-auth.md) | 29 | Mock: sem token; HTTP: Bearer (authApi existente) | **Implementado**: `/auth/register`, `/login`, `/logout`, `/me` e CRUD `/users`; `GET /me/context` é **Planejado — Fase 0/1** (D7) |
| 2 | Chat (channels/conversations/messages) | [02-chat-channels-messages.md](02-chat-channels-messages.md) | 26 | `userId` explícito, sem sessão | **Implementado**: `/channels`, `/conversations`, `/messages` e WebSocket `/ws/{room_kind}/{room_id}`; `userId` do JWT e paridade de campos pendentes no frontend |
| 3 | Reactions / Read-states / Notifications | [03-reactions-readstates-notifications.md](03-reactions-readstates-notifications.md) | 9 | `userId` explícito, sem sessão | **Implementado**: `/reactions`, `/read-states`, `/notifications` |
| 4 | Mail | [04-mail.md](04-mail.md) | 11 | `userId` explícito, sem sessão | **Implementado**: `/mail` (criar, listar, detalhar, marcar lido, editar) |
| 5 | Kanban boards/teams/columns | [05-kanban-boards-teams.md](05-kanban-boards-teams.md) | 2 | Cookie de sessão no adapter HTTP | **Implementado**: `/boards`, `/boards/{id}/columns` e `/teams`; segregação e regras de fluxo são **Planejado — Fase 2** |
| 6 | Kanban cards | [06-kanban-cards.md](06-kanban-cards.md) | 4 | Cookie de sessão no adapter HTTP | **Implementado**: `/cards` (criar, listar, detalhar, atualizar, clonar, `move`, `block`, `unblock`); chave legível e `GET /cards/{id}/history` são **Planejado — Fase 2** |

**Total: 81 operações catalogadas** (snapshot do frontend; não é contagem de rotas do backend).

## Achados transversais (obrigatórios para o backend)

1. **Identidade via JWT apenas.** Em todos os mocks o `userId` chega como parâmetro explícito. No backend, todo ID de usuário deve ser extraído do token JWT — **nunca** por URL/body. `contracts.ts` já prevê: "A real server derives the user from the session".
2. **Paridade de formatos.** Frontend: camelCase + ids prefixados (`user_*`, `ch_*`, `msg_*`, `card_*`, `board_*`, `team_*`). Backend: snake_case + UUID. Mapeamento precisa ser formalizado (relatório de paridade do @dba-postgres).
3. **Ausências globais nos mocks**: paginação, ordenação, filtros server-side (tudo client-side), escopo de auth no realtime.
4. **Operações opcionais até o backend existir**: `createCard`, `cloneCard`, `NotificationRepository.create` (mock implementa; HTTP ausente).
5. **Mail diverge do protótipo Python** `backend/mock_data.py` (snake_case, `is_read: Dict`, pasta `inbox`/`sent`) — ver seção 2 de `04-mail.md`.
6. **Shape User HTTP**: `UserResponse` do backend (confirmado em 2026-11-21) traz `id`, `email`, `cpf`, `telefone`, `idade`, `termos_contrato`, `status_ativo`, `interno_adm`, campos de avatar e datas — **não** traz `name`/`handle`/`color`/`presence`/`workspaceIds` (o adapter preenche defaults). Quebra de paridade a resolver.
7. **Tipo misto**: `readAt` vem número/ISO/null nos mocks vs `ISODate | null` no TS.
8. **Gestão fora do catálogo**: as oito rotas reais `/workspaces/{id}/management/*` não vieram dos mocks; estão documentadas em [`../../apps/ressonant_backend/docs/management-actor-action-matrix.md`](../../apps/ressonant_backend/docs/management-actor-action-matrix.md) e no `openapi.json`.

## Decisões aprovadas — Fase 0, O0

| ID | Decisão aprovada | Estado no monorepo |
|---|---|---|
| **D1** | Configuração: `VITE_API_BASE_URL` como única variável de **URL** (default `/api`, proxy com `rewrite`) e `VITE_DATA_MODE=mock\|http` como **flag de modo** (default `http`); remover as outras sete variáveis | **Planejado — Fase 0/1**: variáveis do frontend, fora deste monorepo; nenhuma `VITE_*` é lida pelo backend |
| **D7** | Bootstrap: adotar `GET /me/context` como canônico; manter `GET /auth/me`; **não** criar `/auth/bootstrap` | `GET /auth/me` **Implementado**; `GET /me/context` **Planejado — Fase 0/1**; `/auth/bootstrap` não será criado |

Fonte das decisões: [Plano Mestre Unificado, §9](../../../docs/PLANO_MESTRE_UNIFICADO.md) (fora do monorepo).

## Planejado — Fase 0/1 (não implementado)

- `GET /me/context` — bootstrap canônico (D7). Hoje existe somente `GET /auth/me`.
- `organizations`, `organization_members`, `invitations` — tabelas e rotas ainda inexistentes.
- `plans`, `subscriptions` — catálogo e billing stub ainda inexistentes.
- Papéis de Dono da Empresa, Admin da organização e Billing Owner — ainda inexistentes; hoje o backend conhece apenas `interno_adm`, owner de workspace e grants de gestão.
- `VITE_API_BASE_URL` e `VITE_DATA_MODE` (D1) — **Planejado — Fase 0/1**, no frontend; nenhuma `VITE_*` existe neste monorepo.
- `GET /auth/bootstrap` — fora de escopo por D7; não implementar.
- Chaves legíveis de card (`ENG-101`), `GET /cards/{id}/history` e WIP/regras persistidas — **Planejado — Fase 2**, fora do O0.

## Fora do escopo desta missão (O0)

- Inventário do legado × catálogo (`07-legacy-inventory.md`), parecer de cybersecurity e desenvolvimento rota por rota pertencem às fases seguintes do [Plano Mestre Unificado](../../../docs/PLANO_MESTRE_UNIFICADO.md), não ao saneamento documental O0.
