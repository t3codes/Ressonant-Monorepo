# Contrato API — Mail (fonte: mocks frontend)

- Fontes lidas (todas existiam):
  - `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/repositories/contracts.ts`
  - `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/mocks/mail.json`
  - `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/src/services/mail.ts`
  - `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-frontend-work/backend/mock_data.py`
  - Evidência de apoio (mesma árvore, somente leitura): `src/types/index.ts`, `src/repositories/mock/createMockRepositories.ts`, `src/repositories/mock/seed.ts`, `src/lib/ids.ts`, `src/lib/mailAttachments.ts`, `src/lib/mailDraft.ts`, `src/lib/mailRecipients.ts`, `src/lib/errors.ts`, `src/hooks/useMail.ts`, `src/views/MailView.tsx`, `src/components/mail/*`, `src/repositories/index.ts`, `src/mocks/index.ts`.
- Extraído por @frontend-react em 2026-11-18 · regra: só evidência, zero invenção.
- Escopo: domínio Mail do **frontend mock**. Nada foi consultado no backend real do monorepo. `backend/mock_data.py` é o protótipo Python que acompanha a cópia do frontend.

---

## 1. Recursos e operações

O domínio Mail é exposto por **duas camadas**:
1. `MailRepository` (`contracts.ts`) — 5 métodos, cada um "mapeado 1:1 para um futuro endpoint HTTP" (comentário literal em `contracts.ts:8-12`).
2. `createMailService(repos)` (`src/services/mail.ts`) — 6 operações de domínio que consomem o repositório.

**Total catalogado: 11 operações** (5 no repositório + 6 no serviço; `markRead` existe nas duas como passthrough).

### 1.1 Tipos de domínio (interfaces TS reais)

`src/types/index.ts:98-108` (anexo base):
```ts
export interface Attachment {
  id: string
  name: string
  sizeBytes: number
  mimeType: string
}

/** An email attachment keeps its content (data URL) so the recipient can download it. */
export interface MailAttachment extends Attachment {
  dataUrl?: string
}
```

`src/types/index.ts:160-184`:
```ts
export interface Email {
  id: string
  senderId: string
  recipientIds: string[]
  subject: string
  body: string
  createdAt: ISODate
  readByIds: string[]
  /** Recipients that received the message in (visible) copy; a subset of recipientIds. */
  ccIds?: string[]
  /** Hidden copy: these people receive the mail but only the sender can see them. */
  bccIds?: string[]
  attachments?: MailAttachment[]
  /** Root email of the conversation; absent on the first message of a thread. */
  threadId?: string
  isReply?: boolean
  forwarded?: boolean
  /** Per-user state: each person trashes, stars and snoozes their own copy. */
  trashedByIds?: string[]
  starredByIds?: string[]
  /** userId -> ISO date when the reminder is due. */
  reminders?: Record<string, ISODate>
}

export type MailFolder = "inbox" | "sent" | "trash" | "favorites" | "reminders"
```

`src/repositories/contracts.ts:102-129`:
```ts
export interface NewEmail {
  senderId: string
  recipientIds: string[]
  ccIds?: string[]
  bccIds?: string[]
  attachments?: MailAttachment[]
  subject: string
  body: string
  threadId?: string
  isReply?: boolean
  forwarded?: boolean
}

/** A change to one user's own view of an email. */
export interface MailUserChange {
  trashed?: boolean
  starred?: boolean
  /** ISO date to set a reminder, or null to clear it. */
  remindAt?: string | null
}

export interface MailRepository {
  listForUser(userId: string): Promise<Email[]>
  getById(id: string): Promise<Email | null>
  create(input: NewEmail): Promise<Email>
  markRead(id: string, userId: string): Promise<Email>
  updateForUser(id: string, userId: string, change: MailUserChange): Promise<Email>
}
```

`src/services/mail.ts:6-18` (payload de envio do serviço):
```ts
export interface SendMailInput {
  senderId: string
  to: string
  cc?: string
  /** Hidden copy (Cco). */
  bcc?: string
  subject: string
  body: string
  attachments?: MailAttachment[]
  /** Email being answered or forwarded; links the new message to its thread. */
  inReplyTo?: string
  forwarded?: boolean
}
```

---

### 1.2 Recurso: MailRepository — `listForUser`

- Interface TS: `listForUser(userId: string): Promise<Email[]>` (`contracts.ts:124`).
- Operação: lista todos os e-mails em que o usuário é remetente **ou** está em `recipientIds`.
- Evidência da implementação mock (`createMockRepositories.ts:231-234`):
```ts
async listForUser(userId) {
  await latency()
  return mail.where(e => e.senderId === userId || e.recipientIds.includes(userId))
},
```
- Autenticação: **sem evidência no mock** — o `userId` é passado explicitamente; não há token/header nesta camada.
- Retorno: `Email[]` não ordenado (a ordenação é feita no serviço).
- Validações observadas: nenhuma (só latência simulada).
- Lacunas: sem paginação, sem filtros server-side, sem busca; a visibilidade de `bcc` não é filtrada aqui (o mock retorna o e-mail inteiro; o recorte de Cco é feito no cliente por `splitRecipients`).

### 1.3 Recurso: MailRepository — `getById`

- Interface TS: `getById(id: string): Promise<Email | null>` (`contracts.ts:125`).
- Implementação mock (`createMockRepositories.ts:235`): `async getById(id) { await latency(); return mail.get(id) }`.
- Autenticação: sem evidência no mock.
- Retorno: `Email | null` (não lança `NotFoundError`).
- Uso real: `services/mail.ts:53-54` (`thread`) e `services/mail.ts:74` (`send`, para resolver o pai de uma resposta).
- Lacunas: não valida se o usuário tem acesso ao e-mail; `getById` é "cego" em relação ao usuário.

### 1.4 Recurso: MailRepository — `create` (envio/respondendo/encaminhando)

- Interface TS: `create(input: NewEmail): Promise<Email>` (`contracts.ts:126`).
- Implementação mock (`createMockRepositories.ts:236-239`):
```ts
async create(input) {
  await latency()
  return mail.insert({ ...input, id: newId("mail"), createdAt: now().toISOString(), readByIds: [input.senderId] })
},
```
- Efeitos observados: `id` e `createdAt` são gerados no servidor; `readByIds` nasce contendo o `senderId`.
- Autenticação: sem evidência no mock (remetente vem de `input.senderId`, não de sessão).
- Exemplo real do mock (`src/mocks/mail.json:2-12`):
```json
{
  "id": "mail_001",
  "senderId": "user_dani",
  "recipientIds": ["user_andreolli"],
  "subject": "Plano Q4 do estúdio",
  "body": "Olá Andreolli,\n\nAnexei o plano Q4 do estúdio. Dois itens precisam da sua entrada: o prazo de embalagem da bakery e as horas compartilhadas no portal do cliente.\n\nPoderia responder até quarta-feira?\n\nDaniela",
  "createdAt": "2026-11-07T08:40:00.000Z",
  "readByIds": []
}
```
- Lacunas: `create` **não emite evento realtime** (diferente de `notifications.create`, que faz `bus.emit({ type: "notification.created", ... })` em `createMockRepositories.ts:208`); não há validação de servidor sobre remetente/recipiente.

### 1.5 Recurso: MailRepository — `markRead`

- Interface TS: `markRead(id: string, userId: string): Promise<Email>` (`contracts.ts:127`).
- Implementação mock (`createMockRepositories.ts:255-260`):
```ts
async markRead(id, userId) {
  await latency()
  const email = mail.get(id)
  if (!email) throw new NotFoundError("Email", id)
  return mail.update(id, { readByIds: [...new Set([...email.readByIds, userId])] })!
},
```
- Semântica: adiciona `userId` a `readByIds` (idempotente, sem duplicar).
- Autenticação: sem evidência no mock.
- Validações observadas: lança `NotFoundError("Email", id)` se inexistente (`contracts.ts:157-162` define a classe).
- Lacunas: não há desmarcar leitura; `markRead` não valida se o usuário é destinatário/remetente.

### 1.6 Recurso: MailRepository — `updateForUser`

- Interface TS: `updateForUser(id: string, userId: string, change: MailUserChange): Promise<Email>` (`contracts.ts:128`).
- Implementação mock (`createMockRepositories.ts:240-254`):
```ts
async updateForUser(id, userId, change) {
  await latency()
  const email = mail.get(id)
  if (!email) throw new NotFoundError("Email", id)
  const toggle = (list: string[] | undefined, on: boolean | undefined) =>
    on === undefined ? list : on ? [...new Set([...(list ?? []), userId])] : (list ?? []).filter(x => x !== userId)
  const reminders = { ...(email.reminders ?? {}) }
  if (change.remindAt === null) delete reminders[userId]
  else if (change.remindAt !== undefined) reminders[userId] = change.remindAt
  return mail.update(id, {
    trashedByIds: toggle(email.trashedByIds, change.trashed),
    starredByIds: toggle(email.starredByIds, change.starred),
    reminders,
  })!
},
```
- Semântica: alterna `trashedByIds`/`starredByIds` por usuário; `remindAt` grava ISO por usuário ou remove com `null`.
- Autenticação: sem evidência no mock.
- Validações observadas: `NotFoundError` se inexistente.
- Lacunas: não há validação de data no repositório (a validação de `remindAt` está no serviço, ver 1.12).

---

### 1.7 Serviço: `list` (pastas)

- Assinatura real (`services/mail.ts:29`): `async list(userId: string, folder: MailFolder): Promise<Email[]>`.
- Derivação de pasta **no cliente** (`services/mail.ts:30-43`):
```ts
const all = await repos.mail.listForUser(userId)
const live = all.filter(e => !e.trashedByIds?.includes(userId))
const pick: Record<MailFolder, Email[]> = {
  inbox: live.filter(e => e.recipientIds.includes(userId)),
  sent: live.filter(e => e.senderId === userId),
  trash: all.filter(e => e.trashedByIds?.includes(userId)),
  favorites: live.filter(e => e.starredByIds?.includes(userId)),
  reminders: live.filter(e => e.reminders?.[userId]),
}
```
- Ordenação: `reminders` ordena pelo `reminders[userId]` ascendente; as demais por `createdAt` decrescente (`newestFirst`, `services/mail.ts:21`).
- Exemplo real do mock que cai em `inbox` para `user_andreolli` (`mail.json:13-26`):
```json
{
  "id": "mail_002",
  "senderId": "user_beatriz",
  "recipientIds": ["user_andreolli", "user_lucas"],
  "subject": "Follow-up do webinar de clientes",
  "body": "Equipe,\n\nO webinar teve 84 inscritos. A pergunta mais comum foi como funcionam as notificações em threads. Coloquei a lista completa no documento de suporte.\n\nBeatriz",
  "createdAt": "2026-11-06T10:20:00.000Z",
  "readByIds": ["user_andreolli"]
}
```
- Autenticação: sem evidência no mock (o `userId` vem de `useCurrentUser()` em `useMail.ts:11`).
- Validações observadas: nenhuma.
- Lacunas: `folder` **não existe** no recurso `Email`; é derivado. `trash` inclui e-mails enviados pelo usuário que ele jogou na lixeira (filtra em `all`, não em `live`).

### 1.8 Serviço: `unreadCount`

- Assinatura real (`services/mail.ts:46`): `async unreadCount(userId: string): Promise<number>`.
- Regra (`services/mail.ts:47-49`): conta `recipientIds.includes(userId) && !readByIds.includes(userId)` entre os não descartados.
- Autenticação: sem evidência no mock.
- Lacunas: não descontar `trashed` de remetente? (o filtro é `visibleTo`, que só exclui `trashedByIds`); não há endpoint dedicado.

### 1.9 Serviço: `thread` (conversa)

- Assinatura real (`services/mail.ts:52`): `async thread(userId: string, emailId: string): Promise<Email[]>`.
- Regra (`services/mail.ts:53-57`): lança `NotFoundError("Email", emailId)` se não existir; a raiz é `e.threadId ?? e.id`; devolve todos os e-mails da conversa **do usuário** (`listForUser`), ordenados do mais antigo para o mais novo.
- Autenticação: sem evidência no mock.
- Exemplo real de encadeamento (`services/mail.ts:87-89`): ao responder, `threadId: parent && !input.forwarded ? threadRoot(parent) : undefined`, `isReply: true`; ao encaminhar, `forwarded: true` e **sem** `threadId`.
- Lacunas: a conversa é montada no cliente; não há endpoint `GET /threads/:id`; `thread` não restringe por pasta (pode expor e-mail da lixeira).

### 1.10 Serviço: `send` (novo/Responder/Reencaminhar)

- Assinatura real (`services/mail.ts:60`): `async send(input: SendMailInput): Promise<Email>`.
- Parsing de endereços (`services/mail.ts:20`): `const parseAddresses = (value) => (value ?? "").split(/[,;\s]+/).filter(Boolean)` — separa por vírgula, ponto-e-vírgula ou espaço.
- Regras observadas (`services/mail.ts:61-90`):
  - `to.length === 0` → `ValidationError("Adicione pelo menos um destinatário.")`.
  - `!input.subject.trim()` → `ValidationError("Adicione um assunto para que os destinatários saibam do que se trata.")`.
  - `attachmentError(attachments)` → `ValidationError` (limites em `mailAttachments.ts:5-7`).
  - todo endereço (to+cc+bcc, deduplicado) é resolvido por `repos.users.getByEmail(a)`; ausentes → `ValidationError("Ninguém em <endereços>. Confira o endereço.")`.
  - deduplicação de papéis: `toIds`, depois `ccIds` fora de `toIds`, depois `bccIds` fora de `toIds`/`ccIds`.
  - `recipientIds` final = `[...toIds, ...ccIds, ...bccIds]`.
  - `ccIds`/`bccIds`/`attachments` só são enviados quando não vazios (`undefined` caso contrário).
  - `subject`/`body` são `.trim()`.
- Autenticação: sem evidência no mock (`senderId` é campo do payload).
- Exemplo real de payload produzido pela UI (`MailView.tsx:116-123` e `MailView.tsx:322-323`):
```ts
await send({
  to: emailsOf(to),
  cc: emailsOf(cc),
  subject: withPrefix("Re: ", email.subject),
  body: content.body,
  attachments: content.attachments,
  inReplyTo: email.id,
})
```
- Encaminhamento (`MailView.tsx:128-136`): `subject: "Fwd: " + subject`, `body` com cabeçalho `---------- Mensagem encaminhada ----------`, `attachments: email.attachments ?? []`, `inReplyTo: email.id`, `forwarded: true`.
- Lacunas: não há validação de tamanho de `subject`/`body` (sem `maxLength`); não há rascunho (draft) persistido; `inReplyTo` não é validado como existente quando `forwarded` é `true` (o mock busca `getById` e, se não achar, `parent = null` silenciosamente em `services/mail.ts:74`).

### 1.11 Serviço: `markRead` (passthrough)

- Assinatura real (`services/mail.ts:93`): `markRead: (id, userId) => repos.mail.markRead(id, userId)`.
- Uso real (`useMail.ts:41-47`): `services.mail.markRead(id, user.id)` seguido de recarga.
- Autenticação: sem evidência no mock.
- Lacunas: ver 1.5.

### 1.12 Serviço: `update` (lixeira/favorito/lembrete)

- Assinatura real (`services/mail.ts:95-98`):
```ts
async update(id, userId, change: MailUserChange) {
  if (change.remindAt && Number.isNaN(Date.parse(change.remindAt))) throw new ValidationError("Escolha uma data válida para o lembrete.")
  return repos.mail.updateForUser(id, userId, change)
},
```
- Validações observadas: `remindAt` precisa ser data parseável; `ValidationError` caso contrário.
- Uso real (`MailView.tsx:282-296`): restaurar `{ trashed: false }`, mover `{ trashed: true, remindAt: null }`; lembrete `{ remindAt: iso }` e limpar `{ remindAt: null }` (`MailView.tsx:336-343`).
- Autenticação: sem evidência no mock.
- Lacunas: não há validar se `remindAt` está no futuro; não há "excluir definitivamente".

---

### 1.13 Autenticação (evidência consolidada)

- Camada Mail (mock + service + hook): **sem evidência de autenticação**. O `userId` é sempre argumento explícito; não há `Authorization`, token, cookie ou header em nenhum arquivo do domínio. O usuário vem de `useCurrentUser()` (`useMail.ts:11`, `MailView.tsx:64`).
- `backend/mock_data.py` (protótipo, não é o domínio Mail):
```python
FAKE_TOKEN = "mock-jwt-token-slack-clone-pro"   # linha 664
def get_current_user() -> User:                  # linhas 667-669
    return USERS["user-1"]
```
  Evidência de auth existe apenas no protótipo (token fixo + usuário fixo), e não há qualquer uso em `INTERNAL_MAIL`.
- Composição real (`src/repositories/index.ts`): `repositories = mockRepositories` (linha 48); `authApi` só existe para modo `http` (linhas 96-100). **Não existe** adapter HTTP para Mail.

---

## 2. Divergências backend/mock_data.py × mocks JSON (evidência literal)

Fonte Python: `backend/mock_data.py` (676 linhas). Modelo `Email` (linhas 633-641):
```python
class Email(BaseModel):
    id: str
    sender_id: str
    recipient_ids: List[str]
    subject: str
    body: str
    created_at: str
    is_read: Dict[str, bool]  # user_id -> read status
    folder: str
```
Dados (linhas 468-519), excerto:
```python
"email-001": {
    "id": "email-001",
    "sender_id": "user-2",
    "recipient_ids": ["user-1", "user-3", "user-5"],
    "subject": "Weekly sync reminder",
    "body": "Hi team, just a reminder our weekly sync is on Thursday at 10am. Please prepare your updates.",
    "created_at": _now() - timedelta(days=3),
    "is_read": {"user-1": False, "user-3": True, "user-5": False},
    "folder": "inbox",
},
```
Força de pasta (linhas 521-524):
```python
# Mark all as folder "inbox" initially except sent
for email in INTERNAL_MAIL.values():
    if email["folder"] != "sent":
        email["folder"] = "inbox"
```

Divergências, uma a uma:

1. **Nomenclatura de campos**: Python `sender_id`, `recipient_ids`, `created_at` (snake_case) × TS/JSON `senderId`, `recipientIds`, `createdAt` (camelCase). Literal: `sender_id` (`mock_data.py:635`) vs `senderId` (`mail.json:4`); `recipient_ids` (`mock_data.py:636`) vs `recipientIds` (`mail.json:5`); `created_at` (`mock_data.py:639`) vs `createdAt` (`mail.json:10`).
2. **Estado de leitura**: Python `is_read: Dict[str, bool]` (`mock_data.py:640`) × TS `readByIds: string[]` (`mail.json:11`). Estruturas diferentes: mapa booleano por usuário vs lista de usuários que leram.
3. **Pasta**: Python tem campo `folder: str` por e-mail (`mock_data.py:641`), com valores efetivos `"inbox"`/`"sent"` (linhas 477/487/497/507/517 e 521-524). TS **não tem** campo `folder`; `MailFolder` é união de 5 valores (`inbox | sent | trash | favorites | reminders`, `types/index.ts:184`) derivada no cliente (`services/mail.ts:32-38`). Python não conhece `trash`, `favorites`, `reminders`.
4. **Cópias (Cc/Cco)**: Python só tem `recipient_ids` (`mock_data.py:636`). TS tem `recipientIds` + `ccIds?` + `bccIds?` (`types/index.ts:163-171`); `recipientIds` é a união To+Cc+Bcc e `ccIds`/`bccIds` são subconjuntos.
5. **Anexos**: Python não tem anexo no modelo `Email`. TS tem `attachments?: MailAttachment[]` (`types/index.ts:172`), com `id`, `name`, `sizeBytes`, `mimeType`, `dataUrl?` (`types/index.ts:98-108`).
6. **Conversa/resposta/encaminhamento**: Python não tem `threadId`, `isReply`, `forwarded`. TS tem os três (`types/index.ts:173-176`).
7. **Estado por usuário**: Python não tem `trashedByIds`, `starredByIds`, `reminders`. TS tem os três (`types/index.ts:177-181`).
8. **IDs**: Python `email-001`…`email-005` (`mock_data.py:469-519`) × mock JSON `mail_001`…`mail_005` (`mail.json:3-63`). Prefixos e contagem divergem.
9. **IDs de usuário**: Python `user-1`…`user-7` (`mock_data.py:41-97`) × mock JSON `user_dani`, `user_andreolli`, `user_beatriz`, `user_lucas`, `user_maria`, `user_caio` (`mail.json`).
10. **Formato de timestamp**: Python `_iso(dt) = dt.isoformat() + "Z"` (`mock_data.py:31-32`) sobre `datetime.utcnow()` (ingênuo, sem tz) — produz frações de segundo quando houver microsegundos. Mock JSON usa ISO fixo com milissegundos e `Z`: `"2026-11-07T08:40:00.000Z"` (`mail.json:10`). TS usa `now().toISOString()` (`createMockRepositories.ts:238`).
11. **Sem operações**: `mock_data.py` é apenas dados + modelos Pydantic; **não define rotas/endpoints** e não tem operações de envio, resposta, thread, mark-read, lixeira, favorito ou lembrete. TS expõe 11 operações (ver seção 1).
12. **Leitura do remetente**: TS `create` inicializa `readByIds: [input.senderId]` (`createMockRepositories.ts:238`); Python `is_read` do `email-001` inclui o destinatário `user-1`, mas o modelo não define regra de remetente.
13. **Sem `MailUserChange`**: o conceito `MailUserChange` (`contracts.ts:116-121`) não existe no protótipo Python.

---

## 3. Formatos globais do domínio

- **IDs**
  - Seed: `mail_001`, `mail_002`… (`mail.json:3,13,27,38,51`).
  - Gerados em runtime: `newId("mail")` → `${prefix}_${Date.now().toString(36)}${counter.toString(36)}${Math.random().toString(36).slice(2, 5)}` (`src/lib/ids.ts:4-7`), ex.: `mail_lq3x9k2a4` (formato documentado no comentário de `ids.ts:3`).
  - Anexos: `att_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}` (`mailAttachments.ts:29`).
  - Usuários: `user_<nome>` (`user_dani`, `user_andreolli`, …).
- **Datas/timestamps**
  - `createdAt` e valores de `reminders`: ISO 8601 UTC com milissegundos e `Z` — `"2026-11-07T08:40:00.000Z"` (`mail.json:10`); tipo TS `ISODate`.
  - Seed é "rebasetado": `rebaseSeed` desloca todo campo cujo nome termina em `At` por um offset, com referência `SEED_REFERENCE = "2026-11-08T12:00:00.000Z"` (`src/mocks/index.ts:30`, `seed.ts:7-20`).
- **Enums**
  - `MailFolder = "inbox" | "sent" | "trash" | "favorites" | "reminders"` (`types/index.ts:184`).
  - Filtro de UI (não é domínio do repositório): `ReadFilter = "all" | "unread" | "read"` (`MailView.tsx:28`).
- **MIME / anexos**
  - `mimeType: string`; `sizeBytes: number`; `name: string`; `dataUrl?: string` (data URL) (`types/index.ts:98-108`).
  - `readAttachment` usa `file.type || "application/octet-stream"` (`mailAttachments.ts:32`).
  - Limites (`mailAttachments.ts:5-7`): `MAX_ATTACHMENTS = 5`, `MAX_ATTACHMENT_BYTES = 1024 * 1024` (1 MiB), `MAX_TOTAL_ATTACHMENT_BYTES = 2 * 1024 * 1024` (2 MiB).
- **Corpo/assunto**: texto puro (markdown no editor de chat; no mail o corpo é texto com quebras `\n`, exemplo `mail.json:9`). Não há HTML.
- **Endereços**: string única com separadores `,`, `;` ou espaço (`services/mail.ts:20`); resolvidos para usuários por `getByEmail`.

---

## 4. Lacunas para o backend resolver

1. **Não existe adapter HTTP para Mail.** `src/repositories/http/` só tem `authApi.ts`, `authBackend.ts`, `createHttpAuthApi.ts`, `createHttpKanbanApi.ts`. O comentário de `contracts.ts:8-12` diz que cada método mapeia 1:1 para um futuro endpoint, mas nenhum endpoint de mail foi definido.
2. **Autenticação/autorização ausente no domínio.** Nenhum método de mail recebe token; `userId` é parâmetro. O backend precisaria derivar o usuário da sessão e autorizar (ex.: só remetente/destinatário podem ler; `bcc` só para o remetente — ver `mailRecipients.ts:3-12`).
3. **Pasta é derivada no cliente.** O backend precisaria decidir se `folder` é campo persistido (como em `mock_data.py`) ou derivado (como no frontend). O protótipo Python diverge: tem `folder` e só `inbox`/`sent`.
4. **Estado de leitura em formato diferente.** `readByIds: string[]` (frontend) × `is_read: Dict[str, bool]` (Python). O backend precisa escolher um e manter `unreadCount` consistente.
5. **Sem paginação/ordenação/filtro server-side.** `listForUser` retorna tudo; `list`, `thread`, filtros de leitura e ordenação são feitos no cliente.
6. **Sem exclusão permanente.** Existe apenas lixeira por usuário (`trashedByIds`); não há purge/restore definitivo.
7. **Sem realtime para mail.** `create` não emite evento no bus; não há notificação de "novo e-mail" no domínio (o protótipo tem `SYSTEM_NOTIFICATIONS` com tipo `"email"`, mas o mock de mail não o cria).
8. **Sem validação de tamanho de `subject`/`body`.** Não há `maxLength` em nenhum componente/serviço.
9. **Anexos em `dataUrl` (base64) no mock.** O backend precisaria de upload/objeto (MinIO/S3) e URL; os limites atuais (5 arquivos, 1 MiB cada, 2 MiB total) são só do cliente.
10. **Rascunho não persistido.** `EMPTY_DRAFT` é só estado local (`mailDraft.ts:16`); não há `draft` no contrato.
11. **`getById` sem controle de acesso.** O mock retorna qualquer e-mail por id; o backend precisa garantir que o usuário participa da conversa.
12. **Python não modela Cc/Bcc, thread, resposta, encaminhamento, lixeira, favorito, lembrete nem anexo** — tudo isso precisa ser desenhado no backend real.

---

## 5. INEXISTENTE

- Nenhum dos quatro arquivos obrigatórios está INEXISTENTE (`contracts.ts`, `mail.json`, `mail.ts`, `backend/mock_data.py` existem e foram lidos).
- **INEXISTENTE:** `src/repositories/http/createHttpMailApi.ts` (ou qualquer adapter HTTP de Mail) — o diretório `src/repositories/http/` contém apenas `authApi.ts`, `authBackend.ts`, `createHttpAuthApi.ts`, `createHttpKanbanApi.ts`.
- **INEXISTENTE:** endpoint/rota de Mail no frontend — não há `fetch`, `axios` ou `new WebSocket()` para mail; tudo passa por `MailRepository` mock.
