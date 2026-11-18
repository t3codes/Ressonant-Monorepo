# Contrato API — Identity / Workspace / Auth (fonte: mocks frontend)
- Fontes lidas: `src/repositories/contracts.ts`, `src/mocks/users.json`, `src/mocks/workspaces.json`, `src/services/auth.ts`, `src/services/profile.ts`, `src/services/workspace.ts` (+ tipos em `src/types/index.ts`, `src/mocks/index.ts`, `src/repositories/mock/createMockRepositories.ts`, `src/repositories/http/authApi.ts`, `src/repositories/http/authBackend.ts`, `src/repositories/http/createHttpAuthApi.ts`, `src/lib/session.ts`, `src/lib/demo.ts`, `src/lib/ids.ts` — lidos como evidência de apoio)
- Extraído por @frontend-react em 2026-11-18 · regra: só evidência, zero invenção

> Regra de escopo: nada aqui afirma nada sobre o backend real. Tudo abaixo é o que os mocks/services do frontend consomem ou declaram. Tipos auxiliares foram lidos em `src/types/index.ts`.

## 1. Recursos e operações

### User
- Interface TS (`src/types/index.ts`, reproduzida):
```ts
export type Presence = "active" | "away" | "dnd" | "offline" | "focused"
export interface User {
  id: string
  name: string
  handle: string
  email: string
  title: string
  /** Hex colour used for the initials avatar when there is no image. */
  color: string
  avatarUrl: string | null
  timezone: string
  presence: Presence
  statusEmoji: string | null
  statusText: string | null
  workspaceIds: string[]
}
```
- Repository (`src/repositories/contracts.ts`):
```ts
export interface UserRepository {
  list(): Promise<User[]>
  getById(id: string): Promise<User | null>
  getByEmail(email: string): Promise<User | null>
  update(id: string, patch: Partial<Pick<User, "presence" | "statusEmoji" | "statusText">>): Promise<User>
}
```
- Operações (repository):
  - `users.list()` — payload: nenhum; retorno: `User[]` (todos, sem filtro; `workspace.ts` filtra por `memberIds` no cliente).
  - `users.getById(id)` — payload: `id: string`; retorno: `User | null`.
  - `users.getByEmail(email)` — payload: `email: string`; retorno: `User | null`; comparação case-insensitive nos dois lados (mock: `u.email.toLowerCase() === email.toLowerCase()`).
  - `users.update(id, patch)` — payload: `Partial<Pick<User, "presence" | "statusEmoji" | "statusText">>`; retorno: `User` atualizado; mock lança `NotFoundError("User", id)` se ausente; mock emite evento `presence.changed`.
- Operações (service `profile.ts`):
  - `profile.get(userId)` — payload: `userId: string`; retorno: `User`; lança `NotFoundError("User", userId)` se `getById` devolver null.
  - `profile.listDirectory()` — payload: nenhum; retorno: `Promise<User[]>` (delega a `users.list()`).
  - `profile.setPresence(userId, presence)` — payload: `presence: Presence`; retorno: `User`.
  - `profile.setStatus(userId, emoji, text)` — payload: `emoji: string | null`, `text: string | null`; retorno: `User`; validação: `text?.trim() || null`, máximo `MAX_STATUS_LENGTH = 80` caracteres, senão `ValidationError`; grava `statusEmoji` somente se `clean || emoji` for truthy (senão `null`), `statusText: clean`.
- Autenticação: sem evidência no mock de `users.*` (o mock não exige sessão). No fluxo HTTP, `GET /users` é admin-only (ver seção auth/session). Erros HTTP mapeados: 401→`AuthError`, 403→`PermissionError`.
- Exemplo real do mock (`src/mocks/users.json`, primeiro registro):
```json
{
  "id": "user_andreolli",
  "name": "Andreolli Costa",
  "handle": "andreolli",
  "email": "andreolli@ressonant.app",
  "title": "Lead de produto",
  "color": "#0B7A7C",
  "avatarUrl": null,
  "timezone": "America/Sao_Paulo",
  "presence": "active",
  "statusEmoji": "🎧",
  "statusText": "Trabalho concentrado até 15:00",
  "workspaceIds": ["ws_ressonant", "ws_atelier"]
}
```
- Formatos: ids `user_<handle>` (`user_andreolli`, `user_lucas`, `user_maria`, `user_pedro`, `user_ana`, `user_beatriz`, `user_caio`, `user_dani`, `user_eduardo`); e-mails `@ressonant.app`; `color` hex `#RRGGBB`; `timezone` IANA (`America/Sao_Paulo`, `Europe/Lisbon`, `America/Recife`); `presence` enum `active|away|dnd|offline|focused` (mocks usam active/away/offline/dnd; `focused` nunca aparece nos dados); `statusEmoji` unicode ou null; `avatarUrl` sempre `null` nos mocks; `workspaceIds` referência a `ws_*`. Nenhuma data em `User`.
- Validações observadas (services/mocks):
  - `profile.setStatus`: trim, máx. 80 chars (`ValidationError`).
  - `auth.login`: e-mail normalizado com `trim()` + regex `/^\S+@\S+\.\S+$/`; senha `typeof === "string" && length > 0`.
  - `users.getByEmail`/`credentials.getByEmail`: case-insensitive.
  - HTTP (`authBackend.ts`): e-mail ≤ 254 chars; senha 8–128; CPF 11 dígitos; telefone 10–11 dígitos; idade inteira 18–120; `termosContrato === true`.
- Lacunas:
  - `User` não tem `createdAt`/`updatedAt` (Workspace tem `createdAt`; User não).
  - `workspaceIds` no User duplica `memberIds` do Workspace; `services/workspace.ts` filtra sempre por `workspace.memberIds`, nunca por `user.workspaceIds` — origem de verdade ambígua no mock.
  - `color` é hex livre; `avatarUrl` nunca preenchido.
  - Backend HTTP (`BackendUser`) não traz name/handle/color/presence/avatarUrl/timezone/workspaceIds — `mapUser` preenche defaults neutros (`presence: status_ativo ? "active" : "offline"`, `workspaceIds: []`, `title: "Administrador"|"Membro"` derivado de `interno_adm`).

### Workspace
- Interface TS (`src/types/index.ts`):
```ts
export interface Workspace {
  id: string
  name: string
  slug: string
  /** One or two characters shown in the workspace rail. */
  initials: string
  color: string
  ownerId: string
  memberIds: string[]
  createdAt: ISODate
}
```
`ISODate = string` (`src/types/index.ts:8`); mocks usam ISO8601 UTC `YYYY-MM-DDTHH:mm:ss.sssZ`.
- Repository (`src/repositories/contracts.ts`):
```ts
export interface WorkspaceRepository {
  list(): Promise<Workspace[]>
  getById(id: string): Promise<Workspace | null>
}
```
- Operações (repository):
  - `workspaces.list()` — payload: nenhum; retorno: `Workspace[]`.
  - `workspaces.getById(id)` — payload: `id: string`; retorno: `Workspace | null`.
- Operações (service `workspace.ts`, recorte Identity):
  - `listWorkspaces(userId)` — payload: `userId: string`; retorno: `Workspace[]` filtrado por `memberIds.includes(userId)`.
  - `listPeople(workspaceId)` — payload: `workspaceId: string`; retorno: `User[]`; se workspace não existe → `[]` (silencioso, sem erro).
  - `getSidebar(workspaceId, userId)` — consome `workspaces`/`users` indiretamente (retorna `SidebarData` com channels/conversations; fora do escopo Identity, citado como consumidor).
  - `createChannel`, `joinChannel`, `startConversation`, `searchChannels` — consomem `workspaceId`, fora do escopo de recursos Identity, citados apenas como consumidores do contrato.
- Autenticação: sem evidência no mock (sem checagem de sessão); filtragem de "meus workspaces" é por `memberIds` no cliente.
- Exemplo real do mock (`src/mocks/workspaces.json`):
```json
{
  "id": "ws_ressonant",
  "name": "Ressonant",
  "slug": "ressonant",
  "initials": "Re",
  "color": "#0B7A7C",
  "ownerId": "user_andreolli",
  "memberIds": ["user_andreolli", "user_lucas", "user_maria", "user_pedro", "user_ana", "user_beatriz", "user_caio"],
  "createdAt": "2026-01-12T12:00:00.000Z"
}
```
Segundo registro: `ws_atelier` / "Atelier Norte" / slug `atelier-norte` / initials `AN` / color `#B4572F` / owner `user_dani` / createdAt `2026-07-11T12:00:00.000Z`.
- Formatos: ids `ws_<slug-ish>` (`ws_ressonant`, `ws_atelier`); `slug` kebab-case (`atelier-norte`); `initials` 1–2 chars ("Re", "AN"); `color` hex; `createdAt` ISO8601 UTC com milissegundos e `Z`.
- Validações observadas: nenhuma validação de input no service para workspaces (apenas leitura). `listPeople` retorna `[]` para workspace inexistente em vez de erro.
- Lacunas:
  - Sem `create`/`update`/`delete`/`archive` de Workspace no contrato — operação inexistente.
  - Sem papéis/permissões por membro (ownerId único; sem roles).
  - `initials` não é derivado nem validado no código (valor manual no JSON).
  - Não há vínculo explícito User↔Workspace além de `memberIds[]` e `user.workspaceIds[]` (duplicação, ver User).

### auth / session
- Evidência de sessão mock (`src/services/auth.ts`, `src/lib/session.ts`):
  - `SESSION_KEY = "ressonant:v1:session"`, `LAST_EMAIL_KEY = "ressonant:v1:last-email"`.
  - Mock: sessão = `user.id` gravado em `storage` (localStorage, "lembrar-me") ou `sessionStore` (sessionStorage); o outro é limpo (`removeItem`) na escrita.
  - `restore()` — mock: lê `SESSION_KEY` de storage/sessionStore → `repos.users.getById(id)`; HTTP: `authApi.restore()`.
  - `login(email, password, remember = false)` — valida e-mail/senha; mock: `users.getByEmail` → `credentials.getByEmail` → compara `credential.password !== password` (texto puro); grava `SESSION_KEY` no storage alvo; se `remember`, grava `LAST_EMAIL_KEY`, senão remove. HTTP: `POST /auth/login` + persiste token (`TOKEN_KEY = "ressonant:v1:token"`) e depois `GET /auth/me` para devolver o usuário.
  - `logout()` — `authApi?.logout()` + remove `SESSION_KEY` dos dois storages. Comentário do código: "o backend é stateless; nada a revogar".
  - `register(input: RegisterInput)` — apenas HTTP; sem `VITE_AUTH_API=http` rejeita com `UnavailableError("Cadastro disponível apenas com o backend real (VITE_AUTH_API=http).")`.
  - `rememberedEmail(): string | null` — lê `LAST_EMAIL_KEY`.
  - `listDemoAccounts(): Promise<User[]>` — sem HTTP: `repos.users.list()`; com HTTP: `authApi.listUsers({ limit: 5 })` e devolve `page.items`; em `PermissionError`/`AuthError` devolve `[]` (tela de login não quebra para não-admin).
- Interface TS do contrato HTTP aprovado (`src/repositories/http/authApi.ts`, cabeçalho: "Auth REST contract for the approved backend surface (`/auth/*`, CRUD `/users`)"):
```ts
export interface RegisterInput {
  email: string
  cpf: string
  telefone: string
  senha: string
  idade: number
  termosContrato: boolean
}
/** Admin-created user (`POST /users`). Flags administrativas ficam só aqui. */
export interface AdminCreateUserInput extends RegisterInput {
  statusAtivo?: boolean
  internoAdm?: boolean
}
/** Editable fields (`PUT /users/{id}`). Senha, CPF e flags administrativas ficam fora. */
export interface UpdateUserInput {
  email: string
  telefone: string
  idade: number
  termosContrato?: boolean | null
}
export interface ListUsersParams {
  skip?: number
  limit?: number
  statusAtivo?: boolean
}
export interface UserListPage {
  items: User[]
  total: number
  skip: number
  limit: number
}
export interface AuthApi {
  /** `POST /auth/register` (público). */
  register(input: RegisterInput): Promise<User>
  /** `POST /auth/login` + persiste o token; devolve o usuário de `GET /auth/me`. */
  login(email: string, password: string, remember?: boolean): Promise<User>
  /** Restaura a sessão a partir do token guardado; `null` quando não há token ou ele expirou. */
  restore(): Promise<User | null>
  /** Descarta o token guardado (o backend é stateless; nada a revogar). */
  logout(): void
  /** `GET /users` (admin), paginado. */
  listUsers(params?: ListUsersParams): Promise<UserListPage>
  /** `GET /users/{userId}` (admin ou o próprio usuário). */
  getUser(userId: string): Promise<User>
  /** `POST /users` (admin). */
  createUser(input: AdminCreateUserInput): Promise<User>
  /** `PUT /users/{userId}` (admin ou o próprio usuário). */
  updateUser(userId: string, input: UpdateUserInput): Promise<User>
  /** `PATCH /users/{userId}/status` (admin). */
  setUserStatus(userId: string, statusAtivo: boolean): Promise<User>
  /** `DELETE /users/{userId}` (admin) — soft delete no backend. */
  deleteUser(userId: string): Promise<void>
}
```
`BackendUser` (payload real do backend, `authBackend.ts`):
```ts
export interface BackendUser {
  id: string
  email: string
  cpf: string
  telefone: string
  idade: number
  termos_contrato: boolean
  status_ativo: boolean
  interno_adm: boolean
  criado_em: string
  atualizado_em: string
}
export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}
```
- Operações (serviço `auth.ts`): `restore()`, `login()`, `logout()`, `register()`, `rememberedEmail()`, `listDemoAccounts()` (detalhadas acima).
- Autenticação:
  - Mock: sem token; sessão = `user.id` em storage; "current user id" = valor de `SESSION_KEY`.
  - HTTP: Bearer token em `Authorization: Bearer <access_token>` (somente quando há token; `auth=true` por padrão); token em `localStorage` (remember) ou `sessionStorage`; `/auth/me` **sem** user id (servidor deriva o caller do token); `TOKEN_KEY = "ressonant:v1:token"`.
  - Erros HTTP mapeados (`createHttpAuthApi.ts`): 401→`AuthError` ("Credenciais inválidas ou sessão expirada." — ou `body.message`), 403→`PermissionError`, 409→`ConflictError` ("E-mail ou CPF já cadastrado."), demais 4xx→`ValidationError`, outros→`UnavailableError`.
- Exemplo real do mock: não há JSON de sessão/credenciais. Credenciais são derivadas em memória (`src/mocks/index.ts`): `demoCredentials = users.map(u => ({ userId: u.id, email: u.email, password: DEMO_PASSWORD }))` com `DEMO_PASSWORD = "ressonant"` (`src/lib/demo.ts`) — todas as contas demo compartilham a mesma senha. Nenhuma senha é gravada em `localStorage` pelo mock ("Credentials stay in memory").
- Formatos: token opaco (`access_token`, `token_type`, `expires_in`); `RegisterInput.cpf`/`telefone` normalizados por `onlyDigits` (`/\D/g`); e-mail normalizado `trim().toLowerCase()` no validador HTTP (o service `auth.login` só faz `trim()`, sem lowercase); `idade` inteiro; `termosContrato` booleano estrito `=== true`.
- Validações observadas (HTTP `validateRegistration`): e-mail regex + ≤254; senha 8–128; CPF 11 dígitos; telefone 10–11 dígitos; idade inteira 18–120; termos obrigatórios. Mock `auth.ts`: e-mail regex `/^\S+@\S+\.\S+$/`, senha não-vazia (sem força mínima no mock — divergência intencional de fluxos).
- Lacunas:
  - Sem endpoint de refresh token / logout server-side (comentário: backend stateless).
  - `authApi` (HTTP) é superfície separada de `contracts.ts` — o composition root escolhe mock vs HTTP via `VITE_AUTH_API=http`; `contracts.ts` não modela `/auth/*`.
  - `register` indisponível no mock (`UnavailableError` forçado).
  - `listDemoAccounts` diverge: mock devolve todos; HTTP devolve no máx. 5 e só para admin (senão `[]`).

### Credential
- Interface TS (`src/types/index.ts`):
```ts
/** Credentials live apart from users so no screen ever receives a password. */
export interface Credential {
  userId: string
  email: string
  password: string
}
```
- Repository (`src/repositories/contracts.ts`):
```ts
export interface CredentialRepository {
  getByEmail(email: string): Promise<Credential | null>
}
```
- Operações:
  - `credentials.getByEmail(email)` — payload: `email: string`; retorno: `Credential | null`; mock compara case-insensitive e mantém em memória (nunca persiste); única operação exposta — sem create/update/delete/troca de senha.
- Autenticação: não se aplica (é o recurso de autenticação); consumido exclusivamente por `auth.login` mock.
- Exemplo real do mock: **não existe arquivo** (`credentials.json` INEXISTENTE). Forma derivada em memória: `{ userId: "user_andreolli", email: "andreolli@ressonant.app", password: "ressonant" }` (senha única demo para todos, `DEMO_PASSWORD`).
- Formatos: `userId` `user_*`; `email` `@ressonant.app`; `password` texto puro (mock).
- Validações observadas: nenhuma validação de conteúdo no repositório mock (apenas `toLowerCase` na comparação).
- Lacunas:
  - Sem hash/verificação real no mock (comparação direta `!==`).
  - Sem operação de alteração de senha, reset ou primeiro acesso.
  - `Credential` não tem `updatedAt`/`mustChangePassword`/`failedAttempts`/`lockedUntil`.

## 2. Formatos globais do domínio (ids, datas, case)
- Ids com prefixo snake/camel por recurso: `user_*`, `ws_*` (mocks: `user_andreolli`…`user_eduardo`; `ws_ressonant`, `ws_atelier`). Ids gerados em runtime usam `newId(prefix)` (`src/lib/ids.ts`), ex. `ntf_*`, `ch_*`, `conv_*`.
- Datas: ISO8601 UTC com milissegundos e sufixo `Z` — `"2026-01-12T12:00:00.000Z"` (workspaces.json), `SEED_REFERENCE = "2026-11-08T12:00:00.000Z"` (`src/mocks/index.ts`). `ISODate = string`. `User` não carrega datas.
- Case: emails comparados case-insensitive (`toLowerCase`) na busca; `auth.login` normaliza só com `trim()` (sem lowercase) antes de chamar o repositório (o repositório normaliza internamente); handle/slug em minúsculas (`andreolli`, `ressonant`, `atelier-norte`); `slug` kebab-case.
- Enums: `Presence = "active" | "away" | "dnd" | "offline" | "focused"`.
- Idioma dos dados: pt-BR (títulos de usuário), UI em pt-BR; enums em inglês.
- Booleanos HTTP snake_case no payload do backend (`termos_contrato`, `status_ativo`, `interno_adm`, `criado_em`, `atualizado_em`) vs camelCase no frontend.

## 3. Lacunas para o backend resolver
1. **Perfil rico ausente no `UserResponse` HTTP** — `BackendUser` não tem name/handle/title/color/avatarUrl/timezone/presence/status/workspaceIds; `mapUser` sintetiza defaults (`title` derivado de `interno_adm`, `workspaceIds: []`), o que quebra a paridade com o mock (que tem perfil completo e workspaces).
2. **Divergência de validação de login** — mock aceita qualquer senha não-vazia e não exige força; HTTP exige senha 8–128 no registro. Sem estratégia única documentada para reset/troca de senha (inexistente nos dois fluxos).
3. **Fonte de verdade User↔Workspace duplicada e sem endpoint** — `user.workspaceIds[]` vs `workspace.memberIds[]`; `services/workspace.ts` filtra por `memberIds`; não há `POST /workspaces`, `GET /workspaces/:id/members` nem vínculo de papéis; o HTTP não expõe workspaces (`mapUser` deixa `workspaceIds: []`).
4. **Sessão sem revogação** — logout é client-side (stateless); sem refresh token; `TOKEN_KEY` em storage sem criptografia; `/auth/me` deriva o caller do token (OK) mas não há evidência de expiração tratada além do 401.
5. **`register` só existe no fluxo HTTP** — mock rejeita com `UnavailableError`; paridade de ambientes quebrada para cadastro público.
6. **Credenciais demo compartilhadas** — `DEMO_PASSWORD = "ressonant"` para todos os usuários; aceitável só para demo; risco se vazar para produção.
7. **`listDemoAccounts` divergente** — mock: todos os usuários; HTTP: `GET /users?limit=5` admin-only, `[]` para não-admin (tela de login silenciosa).
8. **`User` sem timestamps** — impossível ordenar/auditar cadastro pelo contrato mock; backend tem `criado_em`/`atualizado_em` que o frontend descarta no `mapUser`.
9. **`Workspace` sem CRUD/arquivamento/papéis** — apenas leitura no contrato mock; `initials` manual, sem derivação.
10. **Flags administrativas fora do `User`** — `interno_adm`/`status_ativo` vivem só no `BackendUser`/`AdminCreateUserInput`; o tipo `User` do frontend não tem esses campos (sem evidência de como telas admin devem exibi-los via contrato mock).

## 4. INEXISTENTE (arquivos pedidos que não existem)
- `src/mocks/credentials.json` — INEXISTENTE (credenciais derivadas em memória em `src/mocks/index.ts` a partir de `users.json` + `DEMO_PASSWORD`).
- `src/mocks/sessions.json` — INEXISTENTE (sessão vive apenas em `localStorage`/`sessionStorage`, chaves `ressonant:v1:session`, `ressonant:v1:token`, `ressonant:v1:last-email`).
- `src/services/credentials.ts` — INEXISTENTE (acesso a credenciais é via `CredentialRepository` dentro de `auth.ts`).
- `src/services/session.ts` — INEXISTENTE (`src/lib/session.ts` existe e foi lido como apoio; não é um service).
- `src/mocks/workspaces` não tem operações de escrita — não é arquivo ausente, mas capacidade ausente.
