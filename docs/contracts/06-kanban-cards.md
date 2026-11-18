# Contrato API — Kanban (cards/subtasks/checklist/comments/history/custom fields) (fonte: mocks frontend)
- Fontes lidas: `src/repositories/contracts.ts`, `src/mocks/kanban-cards.json` (2463 linhas, lido integralmente), `src/repositories/mock/createMockKanban.ts`, `src/repositories/http/createHttpKanbanApi.ts`, `src/types/kanban.ts`, `src/repositories/mock/cardHistory.ts`, `src/repositories/mock/boardMigrations.ts`, `src/mocks/kanban.ts` (evidência complementar de tipos/seed/validações usadas pelos mocks/services/http-adapter)
- Extraído por @frontend-react em 2026-11-18 · regra: só evidência, zero invenção

## 1. Recursos e operações

### Card (recurso principal)
- Interface TS (`src/types/kanban.ts`):
```ts
export type ISODay = string
export type StatusCategory = "todo" | "in_progress" | "done" | "discarded"
export type CardType = "epic" | "story" | "task" | "bug" | "improvement"
export type Priority = "highest" | "high" | "medium" | "low" | "lowest"
export type SubtaskPriority = "low" | "medium" | "high" | "urgent"

export interface Subtask {
  id: string
  key: string
  title: string
  statusCategory: StatusCategory
  assigneeId: string | null
  /** Opcional: ausente em subtarefas antigas (tratadas como "medium" na UI). */
  priority?: SubtaskPriority
  /** Story points da subtarefa (opcional, 0–100). Cards medem esforço pelo mesmo campo. */
  points?: number
}

export interface ChecklistItem {
  id: string
  text: string
  done: boolean
}

export type LinkRelation = "blocks" | "is_blocked_by" | "relates_to"

export interface CardLink {
  id: string
  relation: LinkRelation
  targetKey: string
}

/** A file on a card. Distinct from the chat `Attachment`, which it extends with where it lives. */
export interface CardAttachment extends Attachment {
  url: string
  uploadedById: string
  createdAt: ISODate
}

export interface Card {
  id: string
  /** Human key, unique per team: `PTA-40`. */
  key: string
  type: CardType
  title: string
  /** Rich text (markdown). */
  context: string
  /** Rich text (markdown). */
  objective: string
  columnId: string
  /** Mirrors the category of the column the card is in. */
  statusCategory: StatusCategory
  priority: Priority
  /** Story points do card (opcional, 0–100). Editável no painel, junto das classificações. */
  points?: number
  assigneeId: string | null
  reporterId: string
  /** The story (or epic) this card belongs to. Stories are the swimlanes. */
  parentId: string | null
  subtasks: Subtask[]
  checklist: ChecklistItem[]
  links: CardLink[]
  labels: string[]
  categories: string[]
  /** Release version the card ships in (a label such as `2026.11`). Not the locking `version`. */
  fixVersion: string | null
  budgetProject: string | null
  startDate: ISODay | null
  dueDate: ISODay | null
  blocked: boolean
  /** Pull request or branch URL, when one exists. */
  prUrl: string | null
  /**
   * Fractional index that orders cards inside a column. Moving a card writes only
   * its own rank, so the rest of the column is never renumbered.
   */
  rank: string
  customFields: Record<string, CustomFieldValue>
  attachments: CardAttachment[]
  watcherIds: string[]
  createdAt: ISODate
  updatedAt: ISODate
  /** Optimistic locking counter. A write carrying an older number is refused. */
  version: number
  /** Comments live embedded in the card; absent in cards persisted before they existed — treat as `[]`. */
  comments?: Comment[]
  /** Change history, appended by the repository on every write; absent before history existed. */
  history?: ActivityEvent[]
  /** Time sessions logged on the card with the start/stop timer; absent before the timer existed. */
  worklogs?: Worklog[]
}
```

- Operações (contrato `KanbanApi`, `src/repositories/contracts.ts`):
  - `createCard(input: NewCardInput, userId: string): Promise<Card>` (opcional no contrato: `createCard?`) — `POST /cards` (ver Shape HTTP). Payload: `NewCardInput`; retorno: `Card` criado.
  - `updateCard(cardId: string, patch: CardPatch, expectedVersion: number, userId: string): Promise<Card>` — `PATCH /cards/:id`. Payload: `cardId`, `patch`, `expectedVersion`; retorno: `Card` atualizado (version incrementada).
  - `moveCard(cardId: string, input: MoveCardInput, userId: string): Promise<Card>` — `POST /cards/:id/move`. Payload: `cardId`, `MoveCardInput`; retorno: `Card` movido (ou card original se sem mudança efetiva, `createMockKanban`: `if (!result.changed) return card`).
  - `cloneCard(cardId: string, userId: string): Promise<Card>` (opcional no contrato: `cloneCard?`) — `POST /cards/:id/clone`. Payload: `cardId`; retorno: novo `Card`.
  - Leitura individual de card (`GET /cards/:id`): **sem evidência** no `KanbanApi`/HTTP adapter/mock. Cards são lidos via `GET /teams/:teamId/board` (`BoardSnapshot.cards`) — fora do escopo deste doc (parte 1), mas é a única evidência de leitura de cards.
  - Delete de card: **sem evidência**.
- Autenticação: mock recebe `userId` explicitamente e checa membership/role (`accessFor`, `canEdit`); `createMockKanban`: "A real server derives the user from the session and checks the team itself; `userId` is passed so the mock can do the same without a session." HTTP adapter não envia `userId` e usa `credentials: "include"` com headers `Content-Type`/`Accept` JSON — ver seção 2. Nenhum token/header específico de auth além disso evidenciado.
- Exemplo real do mock (`src/mocks/kanban-cards.json`, `card_pta_40`):
```json
{
  "id": "card_pta_40",
  "key": "PTA-40",
  "type": "task",
  "title": "Validar certificado ICP-Brasil na assinatura",
  "context": "Hoje o time perde tempo no fluxo de **prescrição**. \"Validar certificado ICP-Brasil na assinatura\" reduz retrabalho.\n\n- Impacto direto no atendimento\n- Depende de alinhamento com produto",
  "objective": "Entregar **Validar certificado ICP-Brasil na assinatura** com testes e documentação, sem regressão no fluxo atual.",
  "columnId": "plataforma_em-andamento",
  "statusCategory": "in_progress",
  "priority": "high",
  "assigneeId": "user_lucas",
  "reporterId": "user_andreolli",
  "parentId": "card_pta_6",
  "subtasks": [
    { "id": "PTA-40-s1", "key": "PTA-40.1", "title": "Levantar requisitos", "statusCategory": "done", "assigneeId": "user_lucas" },
    { "id": "PTA-40-s2", "key": "PTA-40.2", "title": "Implementar", "statusCategory": "done", "assigneeId": "user_lucas" },
    { "id": "PTA-40-s3", "key": "PTA-40.3", "title": "Escrever testes", "statusCategory": "in_progress", "assigneeId": "user_lucas" },
    { "id": "PTA-40-s4", "key": "PTA-40.4", "title": "Revisar com o time", "statusCategory": "todo", "assigneeId": "user_lucas" },
    { "id": "PTA-40-s5", "key": "PTA-40.5", "title": "Publicar", "statusCategory": "todo", "assigneeId": "user_lucas" }
  ],
  "checklist": [],
  "links": [],
  "labels": ["backend", "segurança"],
  "categories": [],
  "fixVersion": "2026.11",
  "budgetProject": "Plataforma 2026",
  "startDate": "2026-11-02",
  "dueDate": "2026-11-12",
  "blocked": false,
  "prUrl": null,
  "customFields": {},
  "attachments": [],
  "watcherIds": [],
  "createdAt": "2026-10-20T12:00:00.000Z",
  "updatedAt": "2026-11-07T12:00:00.000Z",
  "version": 1
}
```
- Exemplo real com `customFields` preenchidos e `prUrl` (`src/mocks/kanban-cards.json`, `card_pta_42`):
```json
{
  "id": "card_pta_42",
  "key": "PTA-42",
  "type": "bug",
  "title": "Assinatura expira antes do prazo em fuso UTC-3",
  "priority": "highest",
  "parentId": "card_pta_6",
  "labels": ["bug", "backend"],
  "fixVersion": "2026.11",
  "startDate": "2026-11-02",
  "dueDate": "2026-11-05",
  "blocked": false,
  "prUrl": "https://example.com/pr/42",
  "customFields": { "iteracao": "Sprint 42", "visibilidade": "Interna" },
  "attachments": [],
  "watcherIds": [],
  "version": 1
}
```
- Exemplo real de epic (`card_pta_94`): `id:"card_pta_94"`, `key:"PTA-94"`, `type:"epic"`, `priority:"highest"`, `parentId:null`, `dueDate:null`, `startDate:"2026-10-01"`.
- Formatos observados no seed: `id` prefixado `card_*` (ex.: `card_pta_40`, `card_est_11`, `card_dad_4`, `card_atl_21`); `key` humano `<PREFIX>-<n>` (ex.: `PTA-40`, `EST-10`); `type` em `{epic, story, task, bug, improvement}`; `priority` em `{highest, high, medium, low, lowest}`; `statusCategory` em `{todo, in_progress, done, discarded}`; `startDate`/`dueDate` `YYYY-MM-DD` ou `null`; `createdAt`/`updatedAt` ISO 8601; `labels` array de strings (podem ser `[]`), `categories` `[]` no seed; `attachments`/`watcherIds`/`links`/`checklist`/`subtasks` arrays (vazios ou preenchidos conforme card); `customFields` objeto `{}` ou chaves string com valores string no seed; `points` ausente no seed (campo opcional no tipo).
- Validações observadas: `version` é contador de optimistic locking; `CardPatch` permite substituir `checklist`, `comments`, `subtasks`, `links`, `watcherIds`, `worklogs` por inteiro, mas **não** `history` (`"history" is deliberately NOT patchable`).
- Lacunas: sem endpoint/contrato de `get` por card nem `delete`; sem evidência de paginação/ordenação de cards além de `rank` no tipo e uso em move/snapshot; `comments/history/worklogs/attachments/watchers/links` não aparecem populados no seed JSON (apenas arrays vazios ou campos ausentes).

### Criar card — `createCard` (`POST /cards`)
- Interface TS (`src/repositories/contracts.ts`):
```ts
/** Body of `POST /cards`. The client never chooses the column: the server puts the card in the team's backlog. */
export interface NewCardInput {
  /** Team whose backlog receives the card. The caller must belong to it and may edit (viewers are refused). */
  teamId: string
  title: string
  /** Free text (markdown); stored as the card's context. */
  description?: string
  type?: CardType
  priority?: Priority
  assigneeId?: string | null
  /** Labels picked by the user; every one must exist in the board's `labels`. */
  labels?: string[]
  dueDate?: ISODay | null
  /** Start date; must not be after `dueDate` when both are set. */
  startDate?: ISODay | null
  /** Reporter; defaults to the caller. Must belong to the team. */
  reporterId?: string
  budgetProject?: string | null
  /** Rich text (markdown), like `description`; max 5000 characters. */
  objective?: string
  /** Story points, 0–100. */
  points?: number
  /** Release version; must exist in the board's `versions`. */
  fixVersion?: string | null
  /** Team custom fields; every key must exist in the board's `customFields`. */
  customFields?: Record<string, CustomFieldValue>
  /** Subtasks born with the card. The server re-keys them (`PTA-97.1`, `PTA-97.2`…) and validates them like a patch. */
  subtasks?: Subtask[]
  checklist?: ChecklistItem[]
  /**
   * Story (História) the card is born under. `null`/omitted = nasce no backlog sem história (exceção
   * explícita); when set, the server refuses a parent that does not exist on the same board or is not a story.
   */
  parentId?: string | null
  /**
   * Accepted so a defensive client can name a column, but ALWAYS ignored: creation never honours it.
   * The repository forces the backlog of `teamId`, so a card can never be born as "Em andamento" etc.
   */
  columnId?: string
}
```
- Operação: `createCard(input, userId) -> Promise<Card>`. HTTP esperado (se exposto): `POST /cards` — **não implementado** no `createHttpKanbanApi.ts` (ver seção 2). Composition root: se `api.createCard` ausente, rejeita com `UnavailableError("Criar cards ainda não é suportado pela API configurada.")`.
- Autenticação: mock valida membro da equipe e permissão de edição (`canEdit`); `userId` usado como reporter default (`reporterId = input.reporterId ?? userId`) e como `actorId` do evento inicial. HTTP: sessão/cookie implícita no adapter (não envia `userId`).
- Exemplo real de payload: **sem evidência** de JSON de request no mock/adapter (chamada interna). Campos aceitos conforme `NewCardInput` acima.
- Exemplo real de retorno/efeito (evidência literal `createMockKanban.ts`): card nasce com `columnId = backlog.id`, `statusCategory = backlog.statusCategory`, `rank = rankAfter(lastRank)`, `key = \`${prefix}${nextNumber}\``, `id = newId("card")`, `version: 1`, `links: []`, `categories: []`, `blocked: false`, `prUrl: null`, `attachments: []`, `watcherIds: []`, `comments: []`, `history` inicial:
```ts
history: [{
  id: newId("evt"), cardId: id, actorId: userId, kind: "created",
  detail: parentId ? `Card criado agregado a ${cards.get(parentId)?.key ?? "história"}` : "Card criado",
  createdAt: nowIso
}]
```
Subtarefas re-chaveadas: `subtasks: (embedded.subtasks ?? []).map((subtask, index) => ({ ...subtask, key: \`${prefix}${nextNumber}.${index + 1}\` }))`.
- Formatos/validações observadas (`createMockKanban.createCard`): `title` trim obrigatório, `<= 160`; `description` (`context`) trim `<= 5000`; `objective` trim `<= 5000`; `type` default `"task"` ∈ `{epic,story,task,bug,improvement}`; `priority` default `"medium"` ∈ `{highest,high,medium,low,lowest}`; `assigneeId` `null` ou membro da equipe; `labels` deduplicadas/trim/filtradas vazias e todas devem existir em `board.labels`; `dueDate`/`startDate` `null` ou regex `^\d{4}-\d{2}-\d{2}$`; `startDate <= dueDate` quando ambos setados; `reporterId` membro da equipe; `budgetProject` trim ou `null`, `<= 120`; `points` sanitizado `0..100` se informado (`sanitizePoints`); `fixVersion` `null` ou existente em `board.versions`; toda chave de `customFields` deve existir em `board.customFields`; `subtasks`/`checklist` validados por `validateEmbedded` (regras em seção "Checklist/Subtarefas/Links/Watchers/Worklogs/Comentários via patch"); `parentId` se setado deve existir no mesmo board e ter `type === "story"`; **`columnId` do cliente é sempre ignorado** e card nasce no backlog; numeração da key usa maior sufixo numérico existente no prefixo do time.
- Lacunas: sem shape HTTP de request/response no adapter (rota ausente); sem evidência de criação com `worklogs`/`comments`/`links`/`attachments`/`watcherIds` no input (apenas `subtasks`, `checklist`, `customFields`).

### Clonar card — `cloneCard` (`POST /cards/:id/clone`)
- Interface TS/contrato: `cloneCard?(cardId: string, userId: string): Promise<Card>` em `KanbanApi`.
- Operação: `POST /cards/:id/clone` (conceitual; **não implementado** no `createHttpKanbanApi.ts`). Retorna novo `Card`. Composition root rejeita se ausente (`"Clonar cards ainda não é suportado pela API configurada."`).
- Autenticação: mock exige acesso ao card/equipe e `canEdit`; `reporterId` do clone vira `userId`.
- Exemplo real de comportamento (evidência literal `createMockKanban.cloneCard`): copia campos descritivos do original (`...card`), gera novo `id/key`, `title = \`Cópia de ${card.title}\`.slice(0,160)`, força backlog (`columnId/statusCategory` do backlog), preserva `parentId` só se pai existe no mesmo board senão `null`, re-gera ids/keys de subtasks (`id: newId("sub")`, `key: \`${key}.${index+1}\``) e checklist (`id: newId("chk")`), zera `links`, `attachments`, `watcherIds`, `comments`; cria `history` inicial `[{ kind:"created", detail: \`Clonado de ${card.key}\` }]`; `rank = rankAfter(lastRank)`, `createdAt/updatedAt = nowIso`, `version: 1`.
- Formatos/validações: requer membro com permissão de edição e existência de coluna Backlog; herda valores do card original (não revalida labels/versões/campos contra board no trecho evidenciado, além de preservar).
- Lacunas: sem HTTP; sem evidência de clonagem de `worklogs` explicitada além de `...card` (tipo permite `worklogs?`; implementação não os limpa explicitamente como limpa comments/links/attachments/watchers — **não inferir comportamento final sem teste**, apenas evidência de campos explicitamente resetados).

### Atualizar card — `updateCard` (`PATCH /cards/:id`)
- Interface TS (`src/types/kanban.ts`):
```ts
export type CardPatch = Partial<
  Pick<
    Card,
    | "title" | "context" | "objective" | "priority" | "assigneeId" | "reporterId" | "labels" | "categories"
    | "fixVersion" | "budgetProject" | "startDate" | "dueDate" | "blocked" | "customFields" | "type" | "points"
    // `checklist`, `comments` and `subtasks` are plain data the client may replace wholesale.
    // `history` is deliberately NOT patchable: the repository appends it from the diff.
    | "checklist" | "comments" | "subtasks" | "links" | "watcherIds" | "worklogs"
  >
>
```
- Operação: `updateCard(cardId, patch, expectedVersion, userId) -> Promise<Card>`. HTTP: `PATCH /cards/:id` com body `{ patch, expectedVersion }` (seção 2).
- Autenticação: mock verifica acesso/permissão de edição e optimistic lock (`card.version !== expectedVersion` ou conflito injetado → `ConflictError`); `userId` usado como ator do histórico.
- Exemplo real de patch/uso: **sem evidência** de payload JSON concreto nos arquivos lidos (chamadas via services/hooks). Campos permitidos são os de `CardPatch`.
- Formatos/validações observadas (`createMockKanban.updateCard`): título se informado não pode ficar vazio após trim (e é salvo trimado); `points` sanitizado se informado; `validateEmbedded(patch)` aplicado; `links` se informados: cada `targetKey` deve existir no board e não pode ser o próprio `key` do card; `version` incrementada, `updatedAt` atualizado, `history` derivado do diff e anexado (cap `MAX_HISTORY`).
- Lacunas: HTTP adapter não envia `userId` (derivado de sessão no servidor real, conforme comentário), mas não há evidência de como o backend real recebe sessão/usuário além de `credentials:"include"`; não há evidência de validação de todos campos de `CardPatch` no mock (ex.: `priority`, `type`, `labels` vs board, `customFields` keys, datas, `assigneeId/reporterId` membership) — diferentemente de `createCard`, `updateCard` valida explicitamente apenas título/points/embedded/links/lock/permissão no trecho lido.

### Mover card — `moveCard` (`POST /cards/:id/move`)
- Interface TS (`src/types/kanban.ts`):
```ts
/** Body of `POST /cards/:id/move`. Exactly one of `beforeCardId` / `afterCardId` anchors the position. */
export interface MoveCardInput {
  toColumnId: string
  beforeCardId?: string | null
  afterCardId?: string | null
  /** Version the client saw; a different value on the server means someone else changed the card. */
  expectedVersion: number
  /** Fields written together with the move (e.g. a new assignee when dropped on another person's lane). */
  fields?: CardPatch
}
```
- Operação: `moveCard(cardId, input, userId) -> Promise<Card>`. HTTP: `POST /cards/:id/move` com body `input` (seção 2).
- Autenticação: mock verifica acesso/permissão, optimistic lock, existência da coluna destino, regras de workflow (`validateTransition`); anexa eventos de histórico (diff de `fields` + evento `moved`).
- Exemplo real: **sem evidência** de payload JSON concreto nos arquivos lidos.
- Validações observadas: coluna destino deve existir no board; transição validada por `validateTransition(card, column, board.workflow, input.fields)`; se sem mudança retorna card original; histórico inclui `moved` com detalhe `Movido para "<column.name>"` e é limitado a `MAX_HISTORY`.
- Lacunas: formato exato de `rank`/ancoragem delegado a `moveCard` de domínio (`../../lib/kanbanDomain`, não lido); sem evidência HTTP de erro/shape além do mapeamento genérico.

### Subtarefas (`Card.subtasks` / `NewCardInput.subtasks` / `CardPatch.subtasks`)
- Interface TS: `Subtask` em `src/types/kanban.ts` (campos `id`, `key`, `title`, `statusCategory`, `assigneeId: string|null`, `priority?: SubtaskPriority`, `points?: number`).
- Operações: criação com card (`createCard` re-chaveia para `${prefix}${nextNumber}.${index+1}`); atualização via `updateCard` com `patch.subtasks` (substituição integral, "plain data the client may replace wholesale"); clonagem copia com novos ids/keys. Sem endpoint dedicado evidenciado.
- Autenticação: herdada das operações de card.
- Exemplo real do mock (`card_pta_40`): ver exemplo acima (5 subtarefas `PTA-40.1`–`PTA-40.5`, status `done/in_progress/todo`, `assigneeId` definido; sem `priority`/`points` explícitos no seed).
- Formatos: `statusCategory` em `{todo,in_progress,done,discarded}`; `priority` opcional em `{low,medium,high,urgent}`; `points` opcional 0–100 (saneado).
- Validações observadas (`validateEmbedded`): array, máx `100` (`MAX_SUBTASKS`); cada item requer `id/key/title` string, `title` trim não vazio `<= 280`; `statusCategory` válido; `priority` se presente válida; `assigneeId` `null` ou string; `points` se presente número finito, saneado por `sanitizePoints` (inteiro arredondado, clamp 0–100). `historyFromDiff` registra adição/remoção/conclusão/reabertura/atualização com contagem concluídas/total.
- Lacunas: sem evidência de valores de `priority/points` preenchidos em subtarefas no seed; sem endpoint próprio.

### Checklist (`Card.checklist` / `NewCardInput.checklist` / `CardPatch.checklist`)
- Interface TS: `ChecklistItem { id: string; text: string; done: boolean }`.
- Operações: criação com card; atualização via `patch.checklist` (substituição integral); clonagem copia com novos ids (`newId("chk")`). Sem endpoint dedicado.
- Exemplo real do mock: todos os cards do seed possuem `"checklist": []` (nenhum item preenchido evidenciado no `kanban-cards.json`).
- Validações observadas (`validateEmbedded`): máx `100` itens; cada item requer `id` string, `text` string, `done` boolean; `text` trim não vazio `<= 280`. Histórico diferencia adição/remoção/conclusão/reabertura/atualização.
- Lacunas: sem exemplo real de item de checklist populado no seed.

### Comentários (`Card.comments` / `CardPatch.comments`)
- Interface TS (`src/types/kanban.ts`):
```ts
export interface Comment {
  id: string
  cardId: string
  authorId: string
  body: string
  createdAt: ISODate
  editedAt: ISODate | null
  parentId: string | null
  reactions: Record<string, string[]>
}
```
- Operações: `Card.comments` é opcional/ausente em cards antigos (tratar como `[]`). `createCard` inicializa `comments: []`; `cloneCard` zera `comments: []`. Atualização via `patch.comments` (substituição integral). Histórico registra `"Comentário adicionado"` quando `patch.comments.length > (card.comments?.length ?? 0)`.
- Autenticação: herdada de `updateCard/createCard/cloneCard`.
- Exemplo real do mock (seed): **ausente** em todos os cards de `src/mocks/kanban-cards.json`; nenhum card contém campo `comments` populado.
- Validações observadas (`validateEmbedded`): máx `200` comentários (`MAX_COMMENTS`); cada comentário deve ter `body/id/authorId` string; `body` trim não vazio e `<= 2000` caracteres. Demais campos (`cardId`, `createdAt`, `editedAt`, `parentId`, `reactions`) exigidos pelo tipo TS mas sem validação explícita adicional no trecho de `validateEmbedded` lido (evidência parcial).
- Lacunas: sem exemplo real populado; sem endpoint dedicado de comentários; sem evidência de validação de `reactions/parentId/editedAt/createdAt/cardId` no mock.

### Histórico (`Card.history` / `ActivityEvent`) — append-only pelo servidor/repositório
- Interface TS (`src/types/kanban.ts`):
```ts
export type ActivityKind = "created" | "moved" | "field_changed" | "commented" | "worklog"

export interface ActivityEvent {
  id: string
  cardId: string
  actorId: string
  kind: ActivityKind
  /** Field or column involved, with the change as plain text. */
  detail: string
  createdAt: ISODate
}
```
- Operações: **não patchável** (`CardPatch` não inclui `history`; "repository appends it from the diff"). Gerado em `createCard` (evento `created`), `cloneCard` (`created`, detalhe `Clonado de ${card.key}`), `updateCard` (`historyFromDiff` + `withHistory`, cap `MAX_HISTORY=100`) e `moveCard` (diff de `fields` + evento `moved`).
- Autenticação: `actorId = userId` (mock).
- Exemplo real (evidência literal de criação, `createMockKanban.ts`):
```ts
{ id: newId("evt"), cardId: id, actorId: userId, kind: "created", detail: "Card criado" /* ou "Card criado agregado a <key história>" */, createdAt: nowIso }
```
Exemplo real de move: `{ id: newId("evt"), cardId, actorId: userId, kind: "moved", detail: \`Movido para "${column.name}"\`, createdAt: at }`.
- Formatos: `kind` em `{created,moved,field_changed,commented,worklog}`; `detail` texto livre derivado (ex.: "Título alterado", "Prioridade: ... → ...", "Subtarefa adicionada (...)", "Tempo registrado: ...", "Comentário adicionado", `Movido para "..."`).
- Validações/garantias observadas: histórico produzido apenas pelo repositório (`historyFromDiff`/`withHistory`); limitado a 100 eventos (`slice(-MAX_HISTORY)`).
- Lacunas: seed JSON não contém `history` em nenhum card; sem endpoint de consulta de histórico separado.

### Worklogs / tempo registrado (`Card.worklogs` / `CardPatch.worklogs`)
- Interface TS (`src/types/kanban.ts`):
```ts
export interface Worklog {
  id: string
  cardId: string
  userId: string
  /** Time spent, in seconds (a start/stop session is rarely a whole number of minutes). */
  seconds: number
  description: string
  startedAt: ISODate
}
```
- Operações: campo opcional; atualização via `patch.worklogs` (substituição integral). `historyFromDiff` adiciona evento `kind:"worklog"` com `detail: \`Tempo registrado: ${formatDuration(added?.seconds ?? 0)}\`` quando tamanho aumenta (usa último item).
- Exemplo real do mock (seed): **ausente** em todos os cards.
- Validações observadas (`validateEmbedded`): máx `500`; cada log requer `id/userId/startedAt` string; `seconds` inteiro entre `1` e `86400` (24h).
- Lacunas: sem exemplo real populado; sem endpoint dedicado; comportamento de clone quanto a `worklogs` não explicitamente resetado no trecho (ver lacuna em "Clonar card").

### Links (`Card.links` / `CardPatch.links`)
- Interface TS: `CardLink { id: string; relation: LinkRelation; targetKey: string }`, `LinkRelation = "blocks" | "is_blocked_by" | "relates_to"`.
- Operações: criação/clonagem inicializa `links: []`; atualização via `patch.links` (substituição integral).
- Exemplo real do mock (seed): `"links": []` em todos os cards.
- Validações observadas: `validateEmbedded` exige máx `50`, `id/targetKey` string, relação válida, sem duplicata por assinatura `${relation}:${targetKey}`; `updateCard` exige que cada `targetKey` exista no board e seja diferente do `key` do próprio card.
- Lacunas: sem exemplo populado.

### Watchers (`Card.watcherIds` / `CardPatch.watcherIds`)
- Interface TS: `watcherIds: string[]`.
- Operações: criação/clonagem inicializa `[]`; atualização via `patch.watcherIds`.
- Exemplo real do mock (seed): `"watcherIds": []` em todos os cards.
- Validações observadas: array de strings, máx `200`, deduplicado (`[...new Set(patch.watcherIds)]`).
- Lacunas: sem exemplo populado.

### Custom fields / QA-Release (`Card.customFields`, `NewCardInput.customFields`, `CardPatch.customFields`, `Board.customFields`)
- Interface TS (`src/types/kanban.ts`, `src/repositories/contracts.ts`): `customFields: Record<string, CustomFieldValue>`; `CustomFieldValue = string | number | boolean | string[] | null`; definições em `Board.customFields: CustomFieldDefinition[]` com tipos `text|select|multiselect|user|date|number|checkbox` e opções.
- Operações: criação aceita `customFields` (toda chave deve existir em `board.customFields`); atualização via `patch.customFields` (substituição integral permitida pelo tipo de patch). Migração idempotente de definições QA/Release em `boardMigrations.ts` (`ensureQaCustomFields`, chaves: `ativacaoFinanceira`, `modulos`, `severidade`, `tipoTeste`, `presencaMigration`, `precisaReview`, `origemBug`, `evidenciaRollback`) — adiciona definições ausentes a boards persistidos usando definições canônicas de `seedBoards[0].customFields`; não altera valores em cards.
- Exemplo real do mock: maioria `{}`; exemplos preenchidos: `card_pta_42` -> `{"iteracao":"Sprint 42","visibilidade":"Interna"}`; `card_pta_45/48/51/54/60/72/81/84/90/93/1609?...` (no seed: `card_pta_45`, `card_pta_48`, `card_pta_51`, `card_pta_54`, `card_pta_60`, `card_pta_72`, `card_pta_81`, `card_pta_84`, `card_pta_90`, `card_pta_93`, `card_est_15`, `card_atl_21`, `card_atl_24` possuem `{"iteracao":"Sprint 42","visibilidade":"Interna"}`).
- Formatos/validações observadas: no `createCard`, chave desconhecida → erro `Campo desconhecido: <key>`; valor tipado conforme `CustomFieldValue`. Sem validação de valor/tipo/opções contra `CustomFieldDefinition` evidenciada no `createMockKanban/updateCard` lidos.
- Lacunas: definições completas (label/type/options/required) dos campos QA/Release e de `iteracao/visibilidade` **não estão** nos arquivos lidos (vêm de `kanban-boards.json`/seed boards não lido aqui; `ensureQaCustomFields` referencia `seedBoards[0].customFields`); sem evidência de validação de valores conforme definição no mock.

## 2. Shape HTTP esperado (`createHttpKanbanApi.ts`) — evidência literal
```ts
import { ConflictError, PermissionError, UnavailableError, ValidationError } from "../../lib/errors"
import type { ApiErrorBody, BoardSnapshot, Card, CardPatch, MoveCardInput, Team } from "../../types/kanban"
import { NotFoundError, type KanbanApi } from "../contracts"

/**
 * `KanbanApi` over REST. It is not the default (there is no backend yet) but it is the proof that the
 * components do not care: switching `VITE_KANBAN_API=http` swaps this in at the composition root.
 * The server derives the user from the session cookie and must validate team membership itself,
 * so `userId` is not sent.
 */
export const createHttpKanbanApi = (baseUrl: string, fetcher: typeof fetch = fetch): KanbanApi => {
  const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
    let response: Response
    try {
      response = await fetcher(`${baseUrl}${path}`, {
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        ...init,
      })
    } catch {
      throw new UnavailableError("Sem conexão com o servidor.")
    }
    if (response.ok) return (await response.json()) as T
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null
    const message = body?.message
    if (response.status === 403) throw new PermissionError(message)
    if (response.status === 404) throw new NotFoundError("Recurso", path)
    if (response.status === 409) throw new ConflictError(message)
    if (response.status === 400 || response.status === 422) throw new ValidationError(message ?? "Dados inválidos.")
    throw new UnavailableError(message)
  }

  return {
    listTeams: (_userId, workspaceId) => request<Team[]>(`/teams?workspaceId=${encodeURIComponent(workspaceId)}`),
    getBoard: teamId => request<BoardSnapshot>(`/teams/${encodeURIComponent(teamId)}/board`),
    updateCard: (cardId, patch: CardPatch, expectedVersion) =>
      request<Card>(`/cards/${encodeURIComponent(cardId)}`, { method: "PATCH", body: JSON.stringify({ patch, expectedVersion }) }),
    moveCard: (cardId, input: MoveCardInput) =>
      request<Card>(`/cards/${encodeURIComponent(cardId)}/move`, { method: "POST", body: JSON.stringify(input) }),
  }
}
```
- Observações de evidência: `createCard` e `cloneCard` **não expostos** no adapter HTTP (e no composition root retornam `UnavailableError` quando ausentes). Erros esperados: `ApiErrorBody { code: "forbidden"|"not_found"|"conflict"|"validation"|"unavailable", message: string }`; mapeamento 403→PermissionError, 404→NotFoundError, 409→ConflictError, 400/422→ValidationError, demais/falha de rede→UnavailableError. Autenticação via `credentials: "include"` (sessão cookie); `userId` não enviado.

## 3. Formatos globais do domínio
- IDs: cards `id` no seed com prefixo `card_` + contexto (ex.: `card_pta_40`, `card_est_11`, `card_dad_4`, `card_atl_21`); eventos/história gerados como `newId("evt")`; subtasks/checklist em clone como `newId("sub")`/`newId("chk")`; novos cards `newId("card")` (formato exato da função `newId` não lido).
- Keys: card humano `<team.keyPrefix>-<n>` (ex.: `PTA-40`, `EST-10`, `DAD-4`, `ATL-21`); subtasks `<cardKey>.<index+1>` (ex.: `PTA-40.1`).
- Datas: `ISODay`/prazo `YYYY-MM-DD` (ex.: `"2026-11-12"`, `"2026-10-01"`) ou `null`; timestamps ISO 8601 (ex.: `"2026-10-20T12:00:00.000Z"`).
- Enums: `CardType` `epic|story|task|bug|improvement`; `Priority` `highest|high|medium|low|lowest`; `SubtaskPriority` `low|medium|high|urgent`; `StatusCategory` `todo|in_progress|done|discarded`; `LinkRelation` `blocks|is_blocked_by|relates_to`; `ActivityKind` `created|moved|field_changed|commented|worklog`.
- Pontos: `points` opcional, `0–100` (saneado para inteiro arredondado e clamp em criação/patch/validação de subtasks).
- Ranks: `rank: string` (ordem fracionária na coluna; detalhes de cálculo em `lib/rank`/`lib/kanbanDomain`, não lidos).
- Custom fields: `Record<string, CustomFieldValue>`; valores observados no seed como strings; chaves QA/Release esperadas por migração: `ativacaoFinanceira, modulos, severidade, tipoTeste, presencaMigration, precisaReview, origemBug, evidenciaRollback` (definições vêm do seed de boards).
- Limites observados: título 160; `description`/`objective` 5000; `budgetProject` 120; subtasks 100 (título 280); checklist 100 (texto 280); comentários 200 (body 2000); links 50; watchers 200; worklogs 500 (1..86400s); histórico 100 eventos retidos.

## 4. Lacunas para o backend resolver
- `createCard` e `cloneCard` não existem no HTTP adapter (`createHttpKanbanApi.ts`) e são opcionais no contrato; definir rotas/shape HTTP, payloads, respostas e erros compatíveis com `NewCardInput`/retorno `Card` e regras de backlog/re-chaveamento/histórico inicial.
- Sem contrato de leitura individual (`GET /cards/:id`) e de exclusão de card; cards só evidenciados via board snapshot.
- `comments`, `history`, `worklogs`, `attachments` (populados), `links` (populados), `watcherIds` (populados) e `checklist` com itens não possuem exemplos reais no seed; modelagem de persistência, APIs dedicadas (se houver) e semântica de substituição integral via `CardPatch` precisam ser confirmadas.
- Definições completas dos custom fields (incluindo QA/Release e campos como `iteracao/visibilidade`) não estão nos arquivos lidos; backend precisa alinhar `Board.customFields`/validação de valores e tipagem de `CustomFieldValue`.
- `updateCard` no mock valida subset de campos (título/points/embedded/links) mas `createCard` valida mais regras (labels/versões/membership/datas/tipo/prioridade/chaves de custom fields); paridade de validação backend x mock não está totalmente especificada.
- Comportamento de `worklogs` na clonagem não está explicitamente definido no código lido (`...card` copiado, sem reset explícito como comments/links/attachments/watchers).
- Detalhes de `rank` (algoritmo/âncoras) e regras de `validateTransition`/`moveCard` de domínio dependem de módulos não lidos (`lib/rank`, `lib/kanbanDomain`).

## 5. INEXISTENTE
- Nenhum dos arquivos obrigatórios declarado como INEXISTENTE (`contracts.ts`, `kanban-cards.json`, `createMockKanban.ts`, `createHttpKanbanApi.ts` existem e foram lidos). Arquivos complementares lidos para evidência de tipos/validações também existem.
