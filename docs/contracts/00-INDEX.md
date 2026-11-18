# Catálogo de Contratos de API — Fonte: mocks do frontend (Fase 1, Passo 1)

- Extraído por 6 lotes de @frontend-react (modelos free OpenCode), em 2026-11-18.
- **Regra**: 100% evidência dos arquivos do frontend (`ressonant-frontend-work`). Zero invenção de rotas/campos.
- **Escopo**: contratos tal como o frontend os consome (`src/repositories/contracts.ts` + `src/mocks/*.json` + `src/services/*`). Mapeamento para rotas REST reais é tarefa do @backend-senior, uma rota por vez, com parecer do @cybersecurity antes da integração.

## Índice por domínio

| # | Domínio | Arquivo | Operações | Auth no mock | Status frente ao backend |
|---|---------|---------|-----------|--------------|--------------------------|
| 1 | Identity / Workspace / Auth | [01-identity-workspace-auth.md](01-identity-workspace-auth.md) | 29 | Mock: sem token; HTTP: Bearer (authApi existente) | Backend já tem auth (register/login/me/users CRUD) |
| 2 | Chat (channels/conversations/messages) | [02-chat-channels-messages.md](02-chat-channels-messages.md) | 26 | `userId` explícito, sem sessão | INEXISTENTE no backend |
| 3 | Reactions / Read-states / Notifications | [03-reactions-readstates-notifications.md](03-reactions-readstates-notifications.md) | 9 | `userId` explícito, sem sessão | INEXISTENTE no backend |
| 4 | Mail | [04-mail.md](04-mail.md) | 11 | `userId` explícito, sem sessão | INEXISTENTE no backend |
| 5 | Kanban boards/teams/columns | [05-kanban-boards-teams.md](05-kanban-boards-teams.md) | 2 | Cookie de sessão no adapter HTTP | INEXISTENTE no backend |
| 6 | Kanban cards | [06-kanban-cards.md](06-kanban-cards.md) | 4 | Cookie de sessão no adapter HTTP | `createCard`/`cloneCard` opcionais (adapter responde `UnavailableError`) |

**Total: 81 operações catalogadas.**

## Achados transversais (obrigatórios para o backend)

1. **Identidade via JWT apenas.** Em todos os mocks o `userId` chega como parâmetro explícito. No backend, todo ID de usuário deve ser extraído do token JWT — **nunca** por URL/body. `contracts.ts` já prevê: "A real server derives the user from the session".
2. **Paridade de formatos.** Frontend: camelCase + ids prefixados (`user_*`, `ch_*`, `msg_*`, `card_*`, `board_*`, `team_*`). Backend: snake_case + UUID. Mapeamento precisa ser formalizado (relatório de paridade do @dba-postgres).
3. **Ausências globais nos mocks**: paginação, ordenação, filtros server-side (tudo client-side), escopo de auth no realtime.
4. **Operações opcionais até o backend existir**: `createCard`, `cloneCard`, `NotificationRepository.create` (mock implementa; HTTP ausente).
5. **Mail diverge do protótipo Python** `backend/mock_data.py` (snake_case, `is_read: Dict`, pasta `inbox`/`sent`) — ver seção 2 de `04-mail.md`.
6. **Shape User HTTP**: `UserResponse` do backend não traz name/handle/color/presence/workspaceIds (adapter preenche defaults) — quebra de paridade a resolver.
7. **Tipo misto**: `readAt` vem número/ISO/null nos mocks vs `ISODate | null` no TS.

## Próximo (Fase 1, Passo 2)

- @backend-senior: inventário do legado (`apps/ressonant_backend`) × este catálogo → `07-legacy-inventory.md`.
- @cybersecurity: revisão pré-build do estado atual + riscos deste catálogo → parecer APROVADO/BLOQUEADO em `.artifacts/cyber/`.
- Só depois: desenvolvimento rota por rota (contrato → rota → QA → cyber → commit local → relatório).
