# Contrato API — Kanban (boards/teams/columns) (fonte: mocks frontend)

- Fontes lidas:
  - `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/repositories/contracts.ts`
  - `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/mocks/kanban.ts`
  - `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/types/kanban.ts`
  - `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/mocks/kanban-boards.json`
  - `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/mocks/kanban-teams.json`
  - `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/services/kanban.ts`
  - (apoio) `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/repositories/http/createHttpKanbanApi.ts`
  - (apoio) `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/repositories/mock/createMockKanban.ts`
  - (apoio) `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/lib/kanbanDomain.ts`
  - (apoio) `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/lib/kanbanFilters.ts`
- Extraído por @frontend-react em 2026-11-18 · regra: só evidência, zero invenção

## 1. Recursos e operações

### Team

- Interface TS (`src/types/kanban.ts`):
  ```ts
  export interface Team {
    id: string
    workspaceId: string
    name: string
    /** Prefix of the card keys of this team, e.g. `PTA` for `PTA-40`. */
    keyPrefix: string
    members: TeamMember[]
  }
  export interface TeamMember {
    userId: string
    role: TeamRole  // "admin" | "member" | "viewer"
  }
  ```
- Operações (via `KanbanApi` em `src/repositories/contracts.ts`):
  - `listTeams(userId: string, workspaceId: string): Promise<Team[]>` — comentado como `` `GET /teams` for one workspace: only the teams the user belongs to. ``
  - HTTP adapter (`src/repositories/http/createHttpKanbanApi.ts`): `GET /teams?workspaceId={workspaceId}` (userId não enviado; servidor deriva do cookie de sessão).
  - Mock (`src/repositories/mock/createMockKanban.ts`): `teams.where(t => t.workspaceId === workspaceId && t.members.some(m => m.userId === userId))`.
  - Service (`src/services/kanban.ts`): `teams: (userId, workspaceId) => api.listTeams(userId, workspaceId)`.
- Autenticação: HTTP adapter usa `credentials: "include"` (cookie de sessão) e envia `Content-Type/Accept: application/json`; o servidor deriva o usuário da sessão. O mock recebe `userId` explicitamente. Comentário do contracts: "A real server derives the user from the session and checks the team itself".
- Exemplo real do mock (`src/mocks/kanban-teams.json`, primeiro item):
  ```json
  {
    "id": "team_plataforma",
    "workspaceId": "ws_ressonant",
    "name": "Plataforma",
    "keyPrefix": "PTA",
    "members": [
      { "userId": "user_andreolli", "role": "admin" },
      { "userId": "user_lucas", "role": "member" },
      { "userId": "user_pedro", "role": "member" },
      { "userId": "user_ana", "role": "member" },
      { "userId": "user_maria", "role": "viewer" }
    ]
  }
  ```
- Formatos: ids `team_*` (ex.: `team_plataforma`, `team_estudio`, `team_dados`, `team_atelier`); `workspaceId` `ws_*` (ex.: `ws_ressonant`, `ws_atelier`); `keyPrefix` string de 3 letras (PTA, EST, DAD, ATL); `role` ∈ {admin, member, viewer}.
- Validações observadas: membership filtrada por `userId` (mock); HTTP 403 → `PermissionError`, 404 → `NotFoundError`.
- Lacunas: não existe operação de criação/edição/exclusão de team nem de gerenciamento de membros (papéis) no contrato; não há `getTeam` individual nem paginação.

### Board

- Interface TS (`src/types/kanban.ts`):
  ```ts
  export interface Board {
    id: string
    teamId: string
    name: string
    /** "Space" of the breadcrumb (Space / Team). */
    space: string
    columns: BoardColumn[]
    workflow: WorkflowRule[]
    customFields: CustomFieldDefinition[]
    /** Release versions offered by the Version field and filter. */
    versions: string[]
    /** Labels offered by the Category/Label field and filter. */
    labels: string[]
  }
  ```
- Sub-tipos relevantes:
  ```ts
  export interface BoardColumn {
    id: string
    boardId: string
    name: string
    /** Position from left to right. */
    order: number
    statusCategory: StatusCategory  // "todo" | "in_progress" | "done" | "discarded"
    /** Soft work-in-progress limit; `null` means unlimited. */
    wipLimit: number | null
    /** Accent colour of the column header. */
    color: string
  }
  export interface WorkflowRule {
    id: string
    toColumnIds?: string[]
    toCategories?: StatusCategory[]
    require: "assignee" | "not_blocked"
    message: string
  }
  export type CustomFieldType = "text" | "select" | "multiselect" | "user" | "date" | "number" | "checkbox"
  export interface CustomFieldOption { value: string; label: string }
  export interface CustomFieldDefinition {
    key: string
    label: string
    type: CustomFieldType
    options?: CustomFieldOption[]
    required?: boolean
  }
  ```
- Operações (via `KanbanApi`):
  - `getBoard(teamId: string, userId: string): Promise<BoardSnapshot>` — comentado como `` `GET /teams/:teamId/board`. Refuses (forbidden) when the user is not on the team. ``
  - HTTP adapter: `GET /teams/{teamId}/board` (sem userId).
  - Mock: valida membership (`team.members.find(m => m.userId === userId)`), senão `PermissionError`; board por `boards.where(b => b.teamId === teamId)[0]`; retorna `BoardSnapshot`.
  - Service (`src/services/kanban.ts`): `board(userId, teamId)` chama `api.getBoard(teamId, userId)` e valida `snapshot.team.id !== teamId` (PermissionError).
- Resposta agregada `BoardSnapshot` (`src/types/kanban.ts`):
  ```ts
  export interface BoardSnapshot {
    team: Team
    board: Board
    cards: Card[]
    /** Pagination per column. The mock returns everything (`nextCursor` is always null). */
    pages: Record<string, ColumnPage>
    /** Role of the requesting user on this team. */
    role: TeamRole
    serverTime: ISODate
  }
  export interface ColumnPage {
    total: number
    nextCursor: string | null
  }
  ```
- Autenticação: mesma evidência de Team (cookie de sessão no HTTP; userId no mock). Refusa não-membro com 403.
- Exemplo real do mock (`src/mocks/kanban-boards.json`, primeiro board, parcial):
  ```json
  {
    "id": "board_plataforma",
    "teamId": "team_plataforma",
    "name": "Pipeline Plataforma",
    "space": "Prescrição",
    "columns": [
      { "id": "plataforma_refinamento", "boardId": "board_plataforma", "name": "Refinamento", "order": 0, "statusCategory": "todo", "wipLimit": null, "color": "#8AA09E" },
      { "id": "plataforma_em-andamento", "boardId": "board_plataforma", "name": "Em Andamento", "order": 5, "statusCategory": "in_progress", "wipLimit": 4, "color": "#2F8FB5" },
      { "id": "plataforma_concluidos", "boardId": "board_plataforma", "name": "Itens Concluídos", "order": 12, "statusCategory": "done", "wipLimit": null, "color": "#2F7D4A" },
      { "id": "plataforma_discarded", "boardId": "board_plataforma", "name": "Discarded", "order": 13, "statusCategory": "discarded", "wipLimit": null, "color": "#8B8F90" }
    ],
    "workflow": [
      { "id": "plataforma_done_needs_assignee", "toColumnIds": ["plataforma_concluidos"], "require": "assignee", "message": "Defina um responsável antes de concluir o card." },
      { "id": "plataforma_progress_not_blocked", "toColumnIds": ["plataforma_em-andamento"], "require": "not_blocked", "message": "Card impedido não pode entrar em Em Andamento. Remova o impedimento antes." }
    ],
    "customFields": [ { "key": "iteracao", "label": "Iteração", "type": "select", "options": [ { "value": "Sprint 41", "label": "Sprint 41" } ] } ],
    "versions": ["2026.10", "2026.11", "2026.12"],
    "labels": ["backend", "bug", "frontend", "infra", "performance", "segurança"]
  }
  ```
- Formatos: ids `board_*` (ex.: `board_plataforma`, `board_estudio`, `board_dados`, `board_atelier`); `columns[].id` segue padrão `{boardSlug}_{columnSlug}` (ex.: `plataforma_em-andamento`); `order` inteiro 0-based crescente; `color` string hex (`#RRGGBB`); `statusCategory` ∈ {todo, in_progress, done, discarded}; `wipLimit` number | null.
- Validações observadas: membership verificada; board buscado por teamId; `pages` calculado por coluna com `nextCursor: null` (mock retorna tudo); falha simulada via `failures.board` → `UnavailableError`.
- Lacunas: sem CRUD de board/column/workflow/customFields/versions/labels; `pages` não pagina (sempre null); sem endpoint para obter board por id (somente por team); sem versionamento/optimistic locking do board.

### Columns (sub-recurso de Board)

- Não existe operação independente de column no `KanbanApi`/service. Columns trafegam embutidas no `Board` (via `getBoard`) e são identificadas por `id` dentro do board.
- Interface TS: `BoardColumn` (acima).
- Operações: nenhuma dedicada (leitura via `getBoard`; mutação de card entre colunas via `moveCard`, parte do domínio de cards, fora do escopo desta parte).
- Autenticação: herdada de `getBoard`.
- Validações observadas: `moveCard` (mock) valida `board.columns.find(c => c.id === input.toColumnId)` senão `ValidationError("Esta coluna não existe mais.")`; `validateTransition` (lib) valida regras de workflow por `toColumnIds`/`toCategories`.
- Lacunas: sem CRUD de colunas (criar/renomear/reordenar/remover), sem persistência de WIP limit, sem reordenação de colunas.

### Agrupamentos e filtros (client-side, expostos em services/lib)

- Não são endpoints. Vivem em `src/lib/kanbanDomain.ts` e `src/lib/kanbanFilters.ts` e operam sobre `cards` do `BoardSnapshot`.
- Tipos (`src/types/kanban.ts`):
  ```ts
  export type GroupBy = "none" | "story" | "assignee" | "priority" | "project"
  export type Density = "compact" | "comfortable"
  export type QuickFilter = "mine" | "blocked" | "unassigned" | "recent"
  export interface BoardFilters {
    query: string
    assigneeIds: string[]
    versions: string[]
    types: CardType[]
    labels: string[]
    priorities: Priority[]
    quick: QuickFilter[]
  }
  export interface BoardView {
    groupBy: GroupBy
    density: Density
    filters: BoardFilters
  }
  ```
- Funções:
  - `EMPTY_FILTERS`, `hasActiveFilters(f)` — `src/lib/kanbanDomain.ts`.
  - `applyFilters(cards, filters, { userId, now })` — filtra por query (title/key), assigneeIds, versions (fixVersion), types, labels, priorities, quick (mine/blocked/unassigned/recent com janela de 7 dias).
  - `groupIntoLanes(items, containers, groupBy, users)` — agrupa em `Lane[]` por none/story/assignee/priority/project; story lanes usam container cards (stories) como cabeçalho.
  - `laneDrop(source, target)` — decide se drop entre lanes é permitido e quais campos escreve (assigneeId/priority/budgetProject).
  - `parseBoardView`/`serializeBoardView`/`parseOpenCard` — `src/lib/kanbanFilters.ts`: persistência da view na URL query (`group`, `density`, `q`, `assignee`, `version`, `type`, `label`, `priority`, `quick`, `card`).
- Autenticação: n/a (client-side).
- Lacunas: filtros/agrupamentos não são persistidos no backend; a URL é a única fonte de verdade da view. Validações de enum (GroupBy/Density/QuickFilter/CardType/Priority) são feitas por allow-list no parse.

## 2. Formatos globais do domínio

- Ids: `team_*`, `board_*`, `boardColumn`/column ids `{slug}_{columnSlug}`, card ids `card_*` (não detalhado aqui), user ids `user_*`, workspace ids `ws_*`.
- Datas: `ISODay = YYYY-MM-DD` (sem hora) para `startDate`/`dueDate`; `ISODate` ISO 8601 com hora para `createdAt`/`updatedAt`/`serverTime`.
- Enums:
  - `TeamRole`: admin | member | viewer
  - `StatusCategory`: todo | in_progress | done | discarded
  - `CardType`: epic | story | task | bug | improvement
  - `Priority`: highest | high | medium | low | lowest
  - `CustomFieldType`: text | select | multiselect | user | date | number | checkbox
  - `GroupBy`: none | story | assignee | priority | project
  - `Density`: compact | comfortable
  - `QuickFilter`: mine | blocked | unassigned | recent
  - `LinkRelation`: blocks | is_blocked_by | relates_to
  - `ActivityKind`: created | moved | field_changed | commented | worklog
- Ordem de colunas: `order: number` (0-based, crescente, left-to-right) dentro de `Board.columns`.
- Erros padrão (`ApiErrorBody`): `{ code: "forbidden" | "not_found" | "conflict" | "validation" | "unavailable", message: string }`; HTTP status mapeados: 403→forbidden, 404→not_found, 409→conflict, 400/422→validation, outros→unavailable.
- Autenticação global: HTTP adapter usa `credentials: "include"` (cookie de sessão); servidor deriva usuário; userId não é enviado pelo cliente.

## 3. Lacunas para o backend resolver

1. Não existem endpoints de criação/edição/exclusão para Team, Board, Column, WorkflowRule, CustomFieldDefinition, versions e labels — apenas leitura agregada via `GET /teams` e `GET /teams/:teamId/board`. O backend precisará definir CRUD (ou decidir que são configuração estática).
2. Paginação por coluna é stub: `ColumnPage.nextCursor` é sempre `null` e o mock retorna todos os cards de uma vez. O backend precisa definir cursor/limit reais por coluna.
3. Autenticação/autorização: o HTTP adapter não envia `userId` (servidor deriva da sessão), enquanto o mock exige `userId` em `listTeams`/`getBoard`. O backend precisa enforçar membership e papéis (admin/member/viewer) por time, inclusive para os endpoints futuros, e definir como o cliente obtém a lista de times de um workspace (hoje filtrada por membership no mock).

## 4. INEXISTENTE

- `GET /teams/:id` individual, `POST/PATCH/DELETE /teams`, `POST/PATCH/DELETE /boards`, `POST/PATCH/DELETE /columns` — não existem no contrato do frontend (KanbanApi não os expõe).
- Endpoints de criação/edição de workflow, customFields, versions, labels — não existem.
- Paginação real (cursor não-nulo) — não implementada (mock sempre null).
- Persistência server-side de filtros/agrupamentos (BoardView) — inexistente; vive apenas na URL client-side.
- Evidência de autenticação além de cookie de sessão (`credentials: "include"`) — não há header Bearer/token no adapter HTTP do kanban; o backend real pode exigir outro esquema (não evidenciado no frontend).