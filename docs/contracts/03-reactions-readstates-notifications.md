# Contrato API — Reactions / Read-states / Notifications (fonte: mocks frontend)
- Fontes lidas: `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/repositories/contracts.ts`; `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/mocks/reactions.json`; `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/mocks/read-states.json`; `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/mocks/notifications.json`; `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/services/notifications.ts` — fontes de apoio lidas para suprir a evidência (somente leitura): `src/types/index.ts`, `src/repositories/mock/createMockRepositories.ts`, `src/services/chat.ts`, `src/services/workspace.ts`, `src/context/NotificationContext.tsx`, `src/mocks/index.ts`.
- Extraído por @frontend-react em 2026-11-18 · regra: só evidência, zero invenção
- Nota de escopo: `contracts.ts` declara que cada método "maps 1:1 to a future HTTP endpoint". Nos arquivos lidos não há rota HTTP, verbo, status code ou payload de rede para reactions/read-states/notifications: o que segue é o contrato de repositório/serviço consumido pelo frontend, não uma especificação de endpoint já existente.

## 1. Recursos e operações

### Reactions
- Interface TS (trecho real de `src/types/index.ts` e `src/repositories/contracts.ts`):
```ts
export interface ReactionRecord {
  id: string
  messageId: string
  userId: string
  emoji: string
  createdAt: ISODate
}

export interface ReactionRepository {
  listByMessageIds(messageIds: string[]): Promise<ReactionRecord[]>
  /** Adds the reaction if missing, removes it otherwise. */
  toggle(input: { messageId: string; userId: string; emoji: string }): Promise<{ active: boolean }>
}
```
- Operações:
  1. `listByMessageIds(messageIds: string[])` — payload: `messageIds: string[]`; retorno: `Promise<ReactionRecord[]>`.
  2. `toggle(input: { messageId: string; userId: string; emoji: string })` — payload: `messageId, userId, emoji`; retorno: `Promise<{ active: boolean }>` (`active: true` = adicionou, `false` = removeu).
  - Operação exposta por `createChatService` (`src/services/chat.ts`): `toggleReaction(messageId, userId, emoji)` — valida `repos.messages.getById(messageId)` (inexistente → `ValidationError("Essa mensagem não existe mais.")`; `deletedAt` → `ValidationError("Essa mensagem foi excluída.")`), depois `assertAccess(message.roomId, message.roomKind, userId)` (→ `PermissionError("Você não faz parte desta conversa.")`), e delega `repos.reactions.toggle({ messageId, userId, emoji })`.
- Autenticação: sem evidência de token/sessão nos contratos lidos; `userId` explícito no input de `toggle`; autorização por membership (`assertAccess`).
- Exemplo real do mock (`src/mocks/reactions.json`, itens `rx_001`–`rx_005`):
```json
[
  { "id": "rx_001", "messageId": "msg_002", "userId": "user_lucas", "emoji": "🎉", "createdAt": "2026-11-06T07:32:00.000Z" },
  { "id": "rx_002", "messageId": "msg_002", "userId": "user_maria", "emoji": "🎉", "createdAt": "2026-11-06T07:32:00.000Z" },
  { "id": "rx_003", "messageId": "msg_002", "userId": "user_ana", "emoji": "🎉", "createdAt": "2026-11-06T07:32:00.000Z" },
  { "id": "rx_004", "messageId": "msg_002", "userId": "user_beatriz", "emoji": "🎉", "createdAt": "2026-11-06T07:32:00.000Z" },
  { "id": "rx_005", "messageId": "msg_002", "userId": "user_caio", "emoji": "🔥", "createdAt": "2026-11-06T07:32:00.000Z" }
]
```
- Formatos: `id` = `rx_<NNN>` (arquivo com 41 registros: `rx_001`–`rx_041`); `messageId` = `msg_<id>`; `userId` = `user_<id>`; `emoji` = string unicode livre; `createdAt` = `ISODate` (ISO 8601 UTC `.000Z`).
- Validações observadas: toggle idempotente (adiciona se ausente, remove se existente); retorno `{ active: boolean }`; notificação de reaction criada para o autor da mensagem quando `message.authorId !== userId` (kind `"reaction"`, `actorId` = reator, `excerpt` = `${emoji} ${snippet(body)}`.trim(), `messageId`, `roomId`, `roomKind`). Reação de usuário sobre a própria mensagem não gera notificação. Validações de serviço: mensagem existe e não excluída; usuário membro da sala.
- Lacunas: unicidade por `(messageId, userId, emoji)` implícita no mock (lookup no array), sem contrato explícito; sem operação de listar reactions por mensagem individual; `{ active }` não carrega contagens/agregados (agregação em `summarizeReactions` → `ReactionSummary { emoji, userIds }`); evento realtime `reaction.changed` emite apenas `{ type, messageId }` (sem emoji/author); sem enum de emojis.

### Read-state
- Interface TS (trecho real de `src/types/index.ts` e `src/repositories/contracts.ts`):
```ts
export interface ReadState {
  id: string
  userId: string
  roomId: string
  lastReadAt: ISODate
}

export interface ReadStateRepository {
  listForUser(userId: string): Promise<ReadState[]>
  markRead(userId: string, roomId: string): Promise<ReadState>
}
```
- Operações:
  1. `listForUser(userId: string)` — payload: `userId`; retorno: `Promise<ReadState[]>`.
  2. `markRead(userId: string, roomId: string)` — payload: `userId, roomId`; retorno: `Promise<ReadState>` (upsert implícito por id `rs_${userId}_${roomId}`).
  - Operações expostas por `createChatService` (`src/services/chat.ts`): `markRead(userId, roomId)` (delega ao repositório) e `getReadMarker(userId, roomId)` (retorna `lastReadAt` ou `null` via `listForUser`).
- Autenticação: sem evidência de token/sessão; `userId` explícito; sem verificação de membership em `markRead`/`listForUser` nos fontes lidos.
- Exemplo real do mock (`src/mocks/read-states.json`, objeto `rs_user_andreolli_ch_general`):
```json
{ "id": "rs_user_andreolli_ch_general", "userId": "user_andreolli", "roomId": "ch_general", "lastReadAt": "2026-11-08T10:20:00.000Z" }
```
- Formatos: `id` = `rs_<user>_<room>` (ex.: `rs_user_andreolli_ch_general`); `roomId` = `ch_*` | `dm_*` | `grp_*`; `lastReadAt` = `ISODate`.
- Validações observadas: upsert implícito (update por id composto, senão insert); `getReadMarker` retorna `null` sem estado; cálculo de unread em `createWorkspaceService.getSidebar` (`lastRead` = mapa `roomId → +new Date(lastReadAt)`; mensagens com `createdAt > lastReadAt`, `authorId !== userId`, `!deletedAt`).
- Lacunas: sem operação de limpar/resetar marcador; sem granularidade por mensagem; sem validação de permissão na escrita; sem `getByRoom` dedicado (varredura em `listForUser`).

### Notifications
- Interface TS (trecho real de `src/types/index.ts` e `src/repositories/contracts.ts`):
```ts
export type NotificationKind = "mention" | "thread_reply" | "reaction" | "invite" | "system" | "card_reminder"

export interface AppNotification {
  id: string
  workspaceId: string
  userId: string
  kind: NotificationKind
  actorId: string | null
  messageId: string | null
  roomId: string | null
  roomKind: RoomKind | null
  excerpt: string
  cardKey?: string | null
  teamId?: string | null
  createdAt: ISODate
  readAt: ISODate | null
}
```
- Operações (`createNotificationService`, `src/services/notifications.ts`):
  1. `list(userId, workspaceId)` — payload: `userId, workspaceId`; retorno: `Promise<AppNotification[]>`; filtra por workspace e ordena por `createdAt` desc.
  2. `markRead(ids: string[])` — payload: `ids: string[]`; retorno: `Promise<void>`.
  3. `markAllRead(userId, workspaceId)` — payload: `userId, workspaceId`; retorno: `Promise<void>`; marca as com `!readAt` (não lidas).
  4. `createCardReminder(input: { userId; workspaceId; teamId; cardKey; title; minutes })` — payload: `userId, workspaceId, teamId, cardKey, title, minutes`; retorno: `Promise<AppNotification>`; exige `repos.notifications.create?` (opcional) senão lança `UnavailableError("Criar notificações ainda não é suportado pela API configurada.")`; kind fixo `"card_reminder"`, `actorId`/`messageId`/`roomId`/`roomKind` nulos, `cardKey`/`teamId` preenchidos; `excerpt` composto; `title` = trim + slice(0, 120).
  5. `isVisible(n: AppNotification, prefs: Preferences["notifications"]): boolean` — visibilidade por kind: `mention` → `prefs.mentions`; `thread_reply` → `prefs.threadReplies`; `reaction` → `prefs.reactions`; default `true`.
- Autenticação: `listForUser(userId)`, `markAllRead(userId, workspaceId)`; realtime event `notification.created` com `notification: AppNotification`; sem token/sessão nos contratos lidos.
- Exemplo real do mock (`src/mocks/notifications.json`, objeto `ntf_001`):
```json
{
  "id": "ntf_001",
  "workspaceId": "ws_ressonant",
  "userId": "user_andreolli",
  "kind": "mention",
  "actorId": "user_lucas",
  "messageId": "msg_022",
  "roomId": "ch_engineering",
  "roomKind": "channel",
  "excerpt": "@andreolli, podemos fazer par no contrato de estado de leitura amanhã? Quero que a busca e o contador de não lidas compartilhem as mesmas primitivas.",
  "createdAt": "2026-11-08T11:00:00.000Z",
  "readAt": null
}
```
- Formatos: `id` = `ntf_<NNN>` (7 registros: `ntf_001`–`ntf_007`); `kind` ∈ {"mention","thread_reply","reaction","invite","system","card_reminder"} (mock: mention, thread_reply, reaction, system); `actorId`/`messageId`/`roomId`/`roomKind` = string | null; `cardKey`/`teamId` = `string | null` (opcionais).
- Validações observadas: `markAllRead` marca apenas as com `!readAt`; contexto (`NotificationContext`) grava `readAt = new Date().toISOString()` no update local; `unreadCount = notifications.filter(n => !n.readAt).length` (pós-filtro de visibilidade por prefs).
- Lacunas: `markRead(ids)` retorna `void`; `markAllRead` por user+workspace (sem lista de ids); `create` é opcional na interface; sem operação de delete/clear; realtime evento com notificação completa.

## 2. Formatos globais do domínio

| Aspecto | Evidência |
| --- | --- |
| Ids | Strings. Reactions `rx_<NNN>`; mensagens `msg_<id>`; notificações `ntf_<NNN>`; read states `rs_<user>_<room>`; usuários `user_*`; workspaces `ws_*`. |
| Datas | `export type ISODate = string` (`src/types/index.ts:8`). Mocks: ISO 8601 UTC com `.000Z`. `ReadState.lastReadAt: ISODate`; `AppNotification.createdAt: ISODate`, `readAt: ISODate \| null`. |
| Enums | `NotificationKind = "mention" \| "thread_reply" \| "reaction" \| "invite" \| "system" \| "card_reminder"`; `RoomKind = "channel" \| "conversation"`; `Presence`; `ChannelVisibility`; `ConversationKind`. |
| Relações | Por id (strings), sem objetos embutidos. `AppNotification.cardKey` referencia card (`PTA-40`) e `teamId` a board. |
| Opcional por `null` | `actorId`, `messageId`, `roomId`, `roomKind`, `cardKey`, `teamId` aceitos como nulos/omitidos; `readAt` nulo = não lida. |
| Ordenação | Notificações: `createdAt` desc (serviço). Reactions: agregação por emoji ordenada por `createdAt` crescente. |
| Erros | `NotFoundError` (`${entity} ${id} was not found`); `PermissionError` e `ValidationError` (pt-BR) em `chat.ts`/`notifications.ts`. |

## 3. Lacunas para o backend resolver

1. **`readAt` com tipo misto nos mocks**: valores numéricos (`2940`, `3080`, `1500`, `7190`) aparecem em `src/mocks/notifications.json`, conflitando com o tipo TS `readAt: ISODate | null` (string) — candidato a bug/lacuna de schema.
2. **Kinds declarados mas não evidenciados**: `invite` e `card_reminder` existem em `NotificationKind`, porém ausentes do mock JSON; `card_reminder` só via `createCardReminder`, sem contrato de notificação para ações de chat (a criação de mention/thread_reply/reaction é atribuída ao "server side of each action").
3. **Sem rota HTTP/real endpoint mapeado**: nenhum path/verbo/payload de rede para reactions/read-states/notifications; ausência total de evidência de autenticação (token/sessão) nos contratos; realtime (`RealtimeGateway`) sem escopo de auth nos eventos.

## 4. INEXISTENTE

- Backend real do ecossistema: reactions/read-states/notifications **não existem** como código (estado **Planejado**) — apenas `GET /health`, `GET /health/ready`, `POST /auth/register`, `POST /auth/login`, `GET /auth/me` e CRUD `/users` estão implementados. Logo, nenhum endpoint HTTP de domínio pode ser mapeado ainda; os contratos acima são exclusivamente do repositório/serviço mock do frontend.
- No frontend, não há arquivos isolados `src/services/reactions.ts` nem `src/services/readStates.ts`: as operações de reactions e read-state vivem em `src/services/chat.ts`; notificações em `src/services/notifications.ts`.
