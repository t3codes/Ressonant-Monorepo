# Contrato API — Chat (channels/conversations/messages) (fonte: mocks frontend)
- Fontes lidas: `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/AGENTS.md`; `src/repositories/contracts.ts`; `src/mocks/channels.json`; `src/mocks/conversations.json`; `src/mocks/messages.json`; `src/services/chat.ts`; `src/types/index.ts` (linhas 1–229, apenas para as definições TS reais importadas por `contracts.ts` — evita inferir campos a partir do JSON).
- Extraído por @frontend-react em 2026-11-18 · regra: só evidência, zero invenção
- Nota de escopo: `contracts.ts` declara explicitamente que "Each method maps 1:1 to a future HTTP endpoint". Nenhuma rota HTTP, status code, payload de rede ou implementação de servidor aparece nos arquivos lidos: o que segue é o contrato de repositório/serviço consumido pelo frontend, não uma especificação de endpoint já existente.

## 1. Recursos e operações

### Channel (canais)
- Interface TS (trecho real de `src/types/index.ts`):
```ts
export type ChannelVisibility = "public" | "private"

export interface Channel {
  id: string
  workspaceId: string
  name: string
  topic: string
  visibility: ChannelVisibility
  memberIds: string[]
  createdBy: string
  createdAt: ISODate
}
```
- Payload de criação (trecho real de `src/repositories/contracts.ts`):
```ts
export interface NewChannel {
  workspaceId: string
  name: string
  topic: string
  visibility: ChannelVisibility
  memberIds: string[]
  createdBy: string
}
```
- Operações (`ChannelRepository`, `src/repositories/contracts.ts`):
  1. `listByWorkspace(workspaceId: string)` — payload: `workspaceId: string`; retorno: `Promise<Channel[]>`
  2. `getById(id: string)` — payload: `id: string`; retorno: `Promise<Channel | null>`
  3. `create(input: NewChannel)` — payload: `workspaceId, name, topic, visibility, memberIds, createdBy`; retorno: `Promise<Channel>`
  4. `addMember(channelId: string, userId: string)` — payload: `channelId: string, userId: string`; retorno: `Promise<Channel>`
- Autenticação: sem evidência de token/sessão/cookie nos arquivos lidos. Autorização observada em `src/services/chat.ts` (`assertAccess`): `const room = roomKind === "channel" ? await repos.channels.getById(roomId) : ...; if (!room || !room.memberIds.includes(userId)) throw new PermissionError("Você não faz parte desta conversa.")` — o `userId` é parâmetro explícito do chamador.
- Exemplo real do mock (`src/mocks/channels.json`, objeto `ch_general`):
```json
{
  "id": "ch_general",
  "workspaceId": "ws_ressonant",
  "name": "general",
  "topic": "Anúncios da empresa e as boas notícias ocasionais",
  "visibility": "public",
  "memberIds": [
    "user_andreolli",
    "user_lucas",
    "user_maria",
    "user_pedro",
    "user_ana",
    "user_beatriz",
    "user_caio"
  ],
  "createdBy": "user_andreolli",
  "createdAt": "2026-01-12T12:00:00.000Z"
}
```
- Exemplo real do mock com `visibility: "private"` (objeto `ch_launch`):
```json
{
  "id": "ch_launch",
  "workspaceId": "ws_ressonant",
  "name": "launch-q4",
  "topic": "Privado: planejamento do lançamento do Q4",
  "visibility": "private",
  "memberIds": [
    "user_andreolli",
    "user_lucas",
    "user_maria",
    "user_beatriz"
  ],
  "createdBy": "user_andreolli",
  "createdAt": "2026-09-29T12:00:00.000Z"
}
```
- Formatos: `id` = `ch_*` (`ch_general`, `ch_product`, `ch_engineering`, `ch_design`, `ch_support`, `ch_launch`, `ch_growth`, `ch_random`, `ch_studio`, `ch_clients`, `ch_finance`); `workspaceId` = `ws_*`; `memberIds`/`createdBy` = `user_*`; `createdAt` = `ISODate` (`export type ISODate = string`), nos mocks sempre ISO 8601 UTC com milissegundos e sufixo `Z`; `visibility` ∈ `{"public","private"}`. O campo `name` difere do `id` (`ch_design` → `"design-crit"`, `ch_support` → `"customer-voice"`, `ch_growth` → `"growth-lab"`). 11 canais no mock: 9 em `ws_ressonant`, 2 em `ws_atelier`.
- Validações observadas: nenhuma no contrato de repositório. No serviço, `assertAccess` exige que o `userId` esteja em `memberIds` para qualquer leitura/escrita em canal. Não há validação de unicidade de `name`, de tamanho de `memberIds`, nem de `createdBy` pertencer ao workspace nos fontes lidos.
- Lacunas: não há operação de atualizar canal (título/tópico/visibilidade), remover membro, arquivar/excluir canal nem listar todos os workspaces de um usuário; `create` não declara regra de permissão (quem pode criar); `addMember` não declara quem pode convidar; `visibility` não é usada em nenhuma validação do serviço lido.

### Conversation (DMs e grupos)
- Interface TS (trecho real de `src/types/index.ts`):
```ts
export type ConversationKind = "direct" | "group"

export interface Conversation {
  id: string
  workspaceId: string
  kind: ConversationKind
  memberIds: string[]
  createdAt: ISODate
}
```
- Payload de criação (trecho real de `src/repositories/contracts.ts`):
```ts
export interface NewConversation {
  workspaceId: string
  memberIds: string[]
}
```
- Operações (`ConversationRepository`, `src/repositories/contracts.ts`):
  5. `listByWorkspace(workspaceId: string)` — payload: `workspaceId: string`; retorno: `Promise<Conversation[]>`
  6. `getById(id: string)` — payload: `id: string`; retorno: `Promise<Conversation | null>`
  7. `create(input: NewConversation)` — payload: `workspaceId: string, memberIds: string[]`; retorno: `Promise<Conversation>`
- Autenticação: sem evidência de token/sessão. `assertAccess` em `chat.ts` usa `repos.conversations.getById(roomId)` e exige `room.memberIds.includes(userId)`, com `userId` passado explicitamente.
- Exemplo real do mock (`src/mocks/conversations.json`, objeto `dm_lucas`):
```json
{
  "id": "dm_lucas",
  "workspaceId": "ws_ressonant",
  "kind": "direct",
  "memberIds": [
    "user_andreolli",
    "user_lucas"
  ],
  "createdAt": "2026-04-22T12:00:00.000Z"
}
```
- Exemplo real do mock com `kind: "group"` (objeto `grp_onboarding`):
```json
{
  "id": "grp_onboarding",
  "workspaceId": "ws_ressonant",
  "kind": "group",
  "memberIds": [
    "user_andreolli",
    "user_lucas",
    "user_maria"
  ],
  "createdAt": "2026-10-19T12:00:00.000Z"
}
```
- Formatos: `id` = `dm_*` (direct) ou `grp_*` (group); `kind` ∈ `{"direct","group"}`; `memberIds` = `user_*`; `createdAt` = `ISODate` (ISO 8601 UTC, `.000Z`). 5 conversas no mock: 4 em `ws_ressonant`, 1 em `ws_atelier`.
- Validações observadas: `assertAccess` exige associação do `userId` a `memberIds`. Nos fontes lidos, `NewConversation` não inclui `kind` nem `createdAt`, e não há regra que impeça criar `direct` com mais de 2 membros ou duplicar uma DM entre os mesmos usuários.
- Lacunas: `create` não recebe `kind` (o contrato não diz como o servidor decidiria `direct` vs. `group`); não há `update`, `addMember`, `removeMember` ou exclusão de conversa; `ConversationView` (`title`, `otherMemberIds`, `unreadCount`) existe em `src/types/index.ts` mas não há operação no contrato que o produza;

### Message (mensagens, threads e anexos)
- Interface TS (trecho real de `src/types/index.ts`):
```ts
export type RoomKind = "channel" | "conversation"

export interface Attachment {
  id: string
  name: string
  sizeBytes: number
  mimeType: string
}

export interface Message {
  id: string
  workspaceId: string
  roomId: string
  roomKind: RoomKind
  authorId: string
  body: string
  createdAt: ISODate
  editedAt: ISODate | null
  deletedAt: ISODate | null
  /** Id of the thread's root message, or null for a top-level message. */
  parentId: string | null
  attachments: Attachment[]
  mentionIds: string[]
}
```
- View model composto pelo serviço (trecho real de `src/types/index.ts`):
```ts
export interface ReactionSummary {
  emoji: string
  userIds: string[]
}

export interface MessageView extends Message {
  reactions: ReactionSummary[]
  replyCount: number
  lastReplyAt: ISODate | null
  replyAuthorIds: string[]
}
```
- Payload de criação/atualização (trecho real de `src/repositories/contracts.ts`):
```ts
export interface NewMessage {
  workspaceId: string
  roomId: string
  roomKind: RoomKind
  authorId: string
  body: string
  parentId: string | null
  attachments: Attachment[]
  mentionIds: string[]
}
...
  update(id: string, patch: { body: string; mentionIds: string[] }): Promise<Message>
  softDelete(id: string): Promise<Message>
```
- Operações (`MessageRepository`, `src/repositories/contracts.ts`):
  8. `listByRoom(roomId: string)` — payload: `roomId: string`; retorno: `Promise<Message[]>`; comentário literal: `/** Top-level messages and thread replies of a room, unordered. */`
  9. `listByWorkspace(workspaceId: string)` — payload: `workspaceId: string`; retorno: `Promise<Message[]>`
  10. `getById(id: string)` — payload: `id: string`; retorno: `Promise<Message | null>`
  11. `create(input: NewMessage)` — payload: `workspaceId, roomId, roomKind, authorId, body, parentId, attachments, mentionIds`; retorno: `Promise<Message>`
  12. `update(id, patch: { body: string; mentionIds: string[] })` — payload: `id: string, patch: { body, mentionIds }`; retorno: `Promise<Message>`
  13. `softDelete(id: string)` — payload: `id: string`; retorno: `Promise<Message>` (exclusão lógica: `deletedAt`)
- Operações expostas por `createChatService` (`src/services/chat.ts`):
  14. `listRoomMessages(roomId, roomKind, userId)` — retorno `Promise<MessageView[]>`; chama `assertAccess`, `listByRoom`, filtra `!m.parentId` e ordena por `createdAt` crescente (`byDate`)
  15. `getThread(rootId, userId)` — retorno `Promise<{ root: MessageView; replies: MessageView[] }>`; `root = getById(rootId)`, `assertAccess(root.roomId, root.roomKind, userId)`, `replies = all.filter(m => m.parentId === rootId).sort(byDate)`
  16. `getMessage(id)` — retorno `Promise<MessageView | null>`; **não** chama `assertAccess` (evidência literal: apenas `getById` + `listByRoom` + `toViews`)
  17. `send(input)` — payload: `{ workspaceId: string; roomId: string; roomKind: RoomKind; authorId: string; body: string; attachments?: Attachment[]; parentId?: string | null }`; retorno `Promise<Message>`; `attachments = input.attachments ?? []`; `mentionIds = extractMentionIds(body, await memberUsers(input.workspaceId))`; delega a `repos.messages.create({...})`
  18. `edit(messageId, userId, body: string)` — retorno `Promise<Message>`; `requireOwn` → `validateBody(body, message.attachments)`; se `trimmed === message.body` retorna a mensagem sem chamar `update`; recalcula `mentionIds`; chama `repos.messages.update(messageId, { body: trimmed, mentionIds })`
  19. `remove(messageId, userId)` — retorno `Promise<Message>`; `requireOwn` → `repos.messages.softDelete(messageId)`
  20. `toggleReaction(messageId, userId, emoji)` — retorno `Promise<{ active: boolean }>`; chama `repos.reactions.toggle({ messageId, userId, emoji })`
  21. `markRead(userId, roomId)` — retorno `Promise<void>`; chama `repos.readStates.markRead(userId, roomId)`
  22. `getReadMarker(userId, roomId)` — retorno `Promise<string | null>`; `states.find(s => s.roomId === roomId)?.lastReadAt ?? null`
- Autenticação/autoria: sem token/sessão. `requireOwn` (trecho real): `const message = await repos.messages.getById(messageId); if (!message) throw new ValidationError("Essa mensagem não existe mais."); if (message.authorId !== userId) throw new PermissionError("Você só pode alterar as suas próprias mensagens."); if (message.deletedAt) throw new ValidationError("Essa mensagem foi excluída.");`
- Validações observadas (`src/services/chat.ts`, trechos reais):
```ts
export const MAX_MESSAGE_LENGTH = 4000

const validateBody = (body: string, attachments: Attachment[]) => {
  const trimmed = body.trim()
  if (!trimmed && attachments.length === 0) throw new ValidationError("Escreva uma mensagem ou anexe um arquivo.")
  if (trimmed.length > MAX_MESSAGE_LENGTH) throw new ValidationError(`As mensagens podem ter no máximo ${MAX_MESSAGE_LENGTH} caracteres.`)
  return trimmed
}
```
  - `assertAccess`: exige `room` existente e `room.memberIds.includes(userId)`, senão `PermissionError("Você não faz parte desta conversa.")`.
  - `toViews`: respostas consideradas apenas se `r.parentId === m.id && !r.deletedAt`; `reactions` agrupadas por `emoji` com `userIds` na ordem de `createdAt`; `replyCount = replies.length`; `lastReplyAt = replies.at(-1)?.createdAt ?? null`; `replyAuthorIds = [...new Set(replies.map(r => r.authorId))]`.
  - `edit` preserva `message.attachments` (não aceita novos anexos no patch) e só grava se o texto mudou.
- Exemplo real do mock — mensagem top-level com anexo (`msg_004`):
```json
{
  "id": "msg_004",
  "workspaceId": "ws_ressonant",
  "roomId": "ch_general",
  "roomKind": "channel",
  "authorId": "user_ana",
  "body": "Lançamento 2.14 está disponível. Notas completas estão no documento de release, e a versão resumida é: busca mais rápida e menos notificações duplicadas.",
  "createdAt": "2026-11-07T10:30:00.000Z",
  "editedAt": null,
  "deletedAt": null,
  "parentId": null,
  "attachments": [
    {
      "id": "msg_004_f1",
      "name": "release-2.14-notes.pdf",
      "sizeBytes": 482113,
      "mimeType": "application/pdf"
    }
  ],
  "mentionIds": []
}
```
- Exemplo real do mock — resposta de thread (`msg_006`, `parentId` preenchido):
```json
{
  "id": "msg_006",
  "workspaceId": "ws_ressonant",
  "roomId": "ch_general",
  "roomKind": "channel",
  "authorId": "user_lucas",
  "body": "Lento também para mim, uns 6 segundos. Vou analisar o plano da query após o almoço.",
  "createdAt": "2026-11-08T09:04:00.000Z",
  "editedAt": null,
  "deletedAt": null,
  "parentId": "msg_005",
  "attachments": [],
  "mentionIds": []
}
```
- Exemplo real do mock — mensagem em conversa (`msg_038`, `roomKind: "conversation"`):
```json
{
  "id": "msg_038",
  "workspaceId": "ws_ressonant",
  "roomId": "dm_lucas",
  "roomKind": "conversation",
  "authorId": "user_lucas",
  "body": "Rápido: você quer que a camada de repositório simule latência?",
  "createdAt": "2026-11-07T10:00:00.000Z",
  "editedAt": null,
  "deletedAt": null,
  "parentId": null,
  "attachments": [],
  "mentionIds": []
}
```
- Exemplo real do mock — mensagem com `mentionIds` (`msg_002`):
```json
{
  "id": "msg_002",
  "workspaceId": "ws_ressonant",
  "roomId": "ch_general",
  "roomKind": "channel",
  "authorId": "user_andreolli",
  "body": "Essa é ótima notícia. Obrigado @caio. O rewrite do fluxo de convite foi trabalho do @lucas e @maria.",
  "createdAt": "2026-11-06T07:30:00.000Z",
  "editedAt": null,
  "deletedAt": null,
  "parentId": null,
  "attachments": [],
  "mentionIds": [
    "user_caio",
    "user_lucas",
    "user_maria"
  ]
}
```
- Formatos: `id` = `msg_NNN` (`msg_001` … `msg_057`); anexo `id` = `msg_NNN_fN` (`msg_004_f1`, `msg_010_f1`, `msg_010_f2`); `workspaceId` = `ws_*`; `roomId` = `ch_*` ou `dm_*`/`grp_*`; `roomKind` ∈ `{"channel","conversation"}`; `authorId`/`mentionIds` = `user_*`; `createdAt`/`editedAt`/`deletedAt` = `ISODate` (ISO 8601 UTC `.000Z`); `editedAt`, `deletedAt` e `parentId` usam `null` quando ausentes (todas as 57 mensagens do mock têm `editedAt: null` e `deletedAt: null`); `attachments[].mimeType` observados: `application/pdf`, `application/octet-stream`, `video/mp4`, `text/csv`, `application/json`, `image/png`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`; `attachments[].sizeBytes` é `number`. 57 mensagens no mock (49 em `ws_ressonant`, 8 em `ws_atelier`).
- Lacunas: nenhum `editedAt`/`deletedAt` preenchido no mock, portanto o formato de escrita desses campos não é evidenciado; `update` recebe `mentionIds` do cliente em vez de derivá-los no servidor; `softDelete` é irreversível no contrato (sem restore/hard delete); `listByRoom` é declarado como "unordered" e a ordenação é feita no cliente (`byDate`); `listByWorkspace` de mensagens existe no contrato mas não é consumida por `chat.ts`; não há paginação/cursor em nenhuma listagem; `getMessage` não valida associação do chamador à sala; `body` não tem limite declarado no contrato de repositório (o limite de 4000 vive apenas no serviço).

### Reaction (reações às mensagens)
- Interface TS (trecho real de `src/types/index.ts`):
```ts
export interface ReactionRecord {
  id: string
  messageId: string
  userId: string
  emoji: string
  createdAt: ISODate
}
```
- Operações (`ReactionRepository`, `src/repositories/contracts.ts`):
  23. `listByMessageIds(messageIds: string[])` — payload: `messageIds: string[]`; retorno: `Promise<ReactionRecord[]>`; comentário literal: `/** Adds the reaction if missing, removes it otherwise. */` aplica-se a `toggle`
  24. `toggle(input: { messageId: string; userId: string; emoji: string })` — payload: `messageId, userId, emoji`; retorno: `Promise<{ active: boolean }>`
- Operação do serviço: `toggleReaction(messageId, userId, emoji)` (já catalogada como item 20) valida mensagem existente e não excluída e chama `assertAccess` antes de `repos.reactions.toggle`.
- Autenticação: sem token/sessão; `toggleReaction` usa `userId` explícito e `assertAccess` por `memberIds`.
- Exemplo real do mock: **sem evidência** — nenhum dos arquivos `src/mocks/*.json` lidos contém reações; apenas o tipo e o contrato existem nos fontes lidos. O serviço produz `ReactionSummary[]` (`{ emoji, userIds }`) via `summarizeReactions`.
- Formatos: `id: string`, `messageId: string`, `userId: string`, `emoji: string`, `createdAt: ISODate` (definição TS); formato de `id` e de `emoji` não evidenciado nos mocks lidos.
- Validações observadas: `toggleReaction` rejeita mensagem inexistente ou com `deletedAt` (`ValidationError("Essa mensagem não existe mais.")`) e exige associação à sala. `summarizeReactions` ordena registros por `createdAt` crescente.
- Lacunas: `emoji` é string livre (sem enum/lista permitida nos fontes lidos); sem contrato de unicidade por `(messageId, userId, emoji)`; sem operação de listar reações por mensagem individual nem de remover explicitamente; ausência de dados de mock impede confirmar o formato de `id` e o comportamento de `active`.

### ReadState (estado de leitura — consumido pelo chat)
- Interface TS (trecho real de `src/types/index.ts`):
```ts
export interface ReadState {
  id: string
  userId: string
  roomId: string
  lastReadAt: ISODate
}
```
- Operações (`ReadStateRepository`, `src/repositories/contracts.ts`):
  25. `listForUser(userId: string)` — payload: `userId: string`; retorno: `Promise<ReadState[]>`
  26. `markRead(userId: string, roomId: string)` — payload: `userId, roomId`; retorno: `Promise<ReadState>`
- Operações do serviço: `markRead(userId, roomId)` (item 21) e `getReadMarker(userId, roomId)` (item 22).
- Autenticação: sem token/sessão; `userId` é parâmetro explícito; nenhuma verificação de `memberIds` em `markRead`/`getReadMarker` (evidência: chamadas diretas a `repos.readStates`).
- Exemplo real do mock: **sem evidência** — não há `read-states.json` entre os arquivos lidos, e nenhum dos 3 mocks lidos contém `lastReadAt`.
- Formatos: `id`, `userId`, `roomId`: `string`; `lastReadAt`: `ISODate`.
- Validações observadas: nenhuma no serviço além da delegação direta; `getReadMarker` retorna `null` quando não há estado para a sala.
- Lacunas: sem validação de associação do usuário à sala em `markRead`; sem contrato de granularidade (por sala, não por mensagem); `getReadMarker` faz varredura em `listForUser` em vez de consulta por `(userId, roomId)` — não há operação `getByRoom` no contrato.

### Notificações e realtime (referências indiretas no domínio chat)
- Trecho real de `src/repositories/contracts.ts` (`NotificationRepository.create?`): "Creates a notification for `input.userId` and announces it on the realtime channel. Used by the card reminders; chat notifications are still created by the server side of each action."
- `RealtimeGateway.subscribe(listener: (event: RealtimeEvent) => void): () => void` (trecho real) — único contrato de realtime nos fontes lidos; nenhum evento de chat nomeado aparece em `chat.ts`.
- Autenticação: sem evidência. Exemplo real do mock: **sem evidência** nos 3 mocks lidos. Formatos: `RealtimeEvent` não lido neste ciclo; não inventado. Lacuna: criação de notificações de chat é atribuída ao "server side of each action" mas não há contrato explícito de payload/rota.

## 2. Formatos globais do domínio

| Aspecto | Evidência |
| --- | --- |
| Ids | Strings. Canais `ch_*`; conversas `dm_*`/`grp_*`; mensagens `msg_*`; anexos `msg_NNN_fN`; usuários `user_*`; workspaces `ws_*`. |
| Datas | `export type ISODate = string` (`src/types/index.ts:8`). Nos mocks: ISO 8601 UTC com 3 dígitos de milissegundo e sufixo `Z`, ex.: `2026-11-06T07:00:00.000Z`. |
| Campos opcionais por `null` | `Message.editedAt`, `Message.deletedAt`, `Message.parentId` — todos `null` nas 57 mensagens do mock. |
| Enums | `ChannelVisibility = "public" \| "private"`; `ConversationKind = "direct" \| "group"`; `RoomKind = "channel" \| "conversation"`. |
| Anexos | `Attachment = { id: string; name: string; sizeBytes: number; mimeType: string }` — apenas metadados; nenhum `dataUrl`/URL de conteúdo no domínio chat (em `src/types/index.ts`, `MailAttachment extends Attachment` é quem acrescenta `dataUrl?`). |
| Relações | Por id (strings), sem objetos embutidos. Trecho real do mock `msg_017`: `"Do lado da API vou combinar: ids como strings, timestamps ISO, relações por id. Nenhum objeto embutido."` |
| Ordenação | Declaradamente "unordered" no repositório (`listByRoom`); o serviço ordena por `+new Date(a.createdAt) - +new Date(b.createdAt)` (`byDate`). |
| Tamanho de `body` | `MAX_MESSAGE_LENGTH = 4000`, aplicado ao texto depois de `.trim()` no serviço. |
| Erros | `NotFoundError` definida em `contracts.ts` (`${entity} ${id} was not found`); `PermissionError` e `ValidationError` usadas em `chat.ts` com mensagens em português (trechos literais nas seções acima). |

## 3. Lacunas para o backend resolver

1. **Nenhuma rota HTTP especificada nos fontes lidos.** `contracts.ts` afirma que cada método "maps 1:1 to a future HTTP endpoint", mas não há caminho, verbo, status code nem payload de rede para channels/conversations/messages/reactions/readStates.
2. **Autenticação/autoria não resolvidas no contrato.** `userId` é passado explicitamente pelo chamador em todas as operações; não há token/sessão nos fontes lidos. Além disso, `getMessage(id)` não chama `assertAccess`, e `markRead`/`getReadMarker` também não — mensagens podem ser lidas por id sem verificação de associação à sala.
3. **Regras de negócio vivem no serviço, não no contrato de dados.** Trim, limite de 4000 caracteres, "mensagem ou anexo", autoria em `edit`/`remove`, extração de `mentionIds` a partir dos membros do workspace e exclusão lógica estão apenas em `chat.ts`. Um adapter HTTP que implemente `MessageRepository` diretamente poderia burlá-las — `update` aceita `mentionIds` e `softDelete` aceita qualquer `id` sem checar autor.
4. **Sem paginação, cursor ou filtro** em `listByRoom`, `listByWorkspace` (mensagens), `listByWorkspace` (canais/conversas) ou `listByMessageIds`; ordenação é feita no cliente.
5. **CRUD incompleto:** canais não têm update/removeMember/archive; conversas não têm `kind` no payload de criação nem update/remoção de membros; mensagens não têm restore/hard delete; reações não têm listagem por mensagem nem remoção explícita.
6. **Ausência de evidência de mock** para reações e read states, e nenhum `editedAt`/`deletedAt` preenchido — o formato de escrita desses campos e o retorno de `toggle({ active })` não podem ser confirmados.
7. **Anexos são só metadados** (`id`, `name`, `sizeBytes`, `mimeType`): não há contrato de upload nem de URL de download para mensagens.
8. **Notificações de chat** são atribuídas ao "server side of each action" em `contracts.ts`, mas não existe payload/contrato explícito; `RealtimeGateway.subscribe` é genérico, sem eventos de chat nomeados nos fontes lidos.

## 4. INEXISTENTE

Nenhum dos 5 arquivos obrigatórios solicitados está ausente. Não há entradas `INEXISTENTE: <caminho>` a declarar. (Ausências de evidência dentro dos mocks — reações, read states, `editedAt`/`deletedAt` preenchidos — estão registradas nas seções 1 e 3 como "sem evidência", sem inferência.)
