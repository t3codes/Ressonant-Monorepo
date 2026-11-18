# ressonant_collections

Coleção de requisições da **Ressonant API** (FastAPI) para importar no **Postman** ou no **Insomnia**.
Este app **não é executável**: não é um serviço FastAPI, não tem compose, não tem Dockerfile e não sobe nada.
Contém apenas artefatos de teste/coleção (JSON/YAML) gerados a partir de [`../ressonant_backend/openapi.json`](../ressonant_backend/openapi.json).

## Conteúdo

```
postman/
  Ressonant API.postman_collection.json      # Collection Postman v2.1 ({info, item[], variable[]})
  Ressonant Local Dev.postman_environment.json  # Environment Postman (desenvolvimento local)
insomnia/
  Ressonant API.insomnia.yaml                # Export Insomnia v4 (YAML, __export_format: 4)
```

Cobertura (12 requests, organizadas nas pastas **Health**, **Auth** e **Users**):

| Pasta  | Request | Método | Rota | Body / Notas |
|--------|---------|--------|------|--------------|
| Health | Health (liveness)           | GET    | `/health`                  | sem body, sem auth |
| Health | Ready (readiness)           | GET    | `/health/ready`            | sem body, sem auth |
| Auth   | Register                    | POST   | `/auth/register`           | `UserRegister` — salva `userId` no script de teste |
| Auth   | Login                       | POST   | `/auth/login`              | `LoginRequest` — salva `accessToken` no script de teste |
| Auth   | Me                          | GET    | `/auth/me`                 | Bearer `{{accessToken}}` |
| Users  | Create User (admin)         | POST   | `/users`                   | `UserCreate` (UserRegister + `status_ativo`, `interno_adm`) — salva `userId` |
| Users  | Create Admin User (interno_adm) | POST | `/users`                   | exemplo com `interno_adm: true` (ajuste o e-mail) |
| Users  | List Users                  | GET    | `/users?skip=&limit=&status_ativo=` | query params; `status_ativo` vem **desabilitado** por padrão |
| Users  | Get User                    | GET    | `/users/{{userId}}`        | admin ou o próprio usuário |
| Users  | Update User                 | PUT    | `/users/{{userId}}`        | `UserUpdate` (email, telefone, idade, termos_contrato) |
| Users  | Set User Status             | PATCH  | `/users/{{userId}}/status` | `UserStatusUpdate` (`status_ativo`) |
| Users  | Delete User (soft delete)   | DELETE | `/users/{{userId}}`        | 204 sem corpo |

## Corpos das requisições (fiéis ao OpenAPI)

```jsonc
// POST /auth/register — UserRegister (required: email, cpf, telefone, senha, idade, termos_contrato)
{ "email": "usuario@example.com", "cpf": "12345678901", "telefone": "11987654321",
  "senha": "SenhaForte123", "idade": 30, "termos_contrato": true }

// POST /auth/login — LoginRequest (required: email, senha)
{ "email": "usuario@example.com", "senha": "SenhaForte123" }

// POST /users — UserCreate (UserRegister + status_ativo=true, interno_adm=false)
{ "email": "usuario@example.com", "cpf": "12345678901", "telefone": "11987654321",
  "senha": "SenhaForte123", "idade": 30, "termos_contrato": true,
  "status_ativo": true, "interno_adm": false }

// PUT /users/{userId} — UserUpdate (required: email, telefone, idade; termos_contrato opcional/nulo)
{ "email": "usuario.atualizado@example.com", "telefone": "11987654321",
  "idade": 31, "termos_contrato": true }

// PATCH /users/{userId}/status — UserStatusUpdate (required: status_ativo)
{ "status_ativo": false }
```

Regras de validação relevantes: `senha` 8–128 caracteres; `idade` entre 18 e 120; `cpf` aceita com ou sem máscara (armazenado só dígitos); `telefone` com DDD (10 ou 11 dígitos); `termos_contrato` boolean.

## Como importar no Postman

1. `Import` → selecione `postman/Ressonant API.postman_collection.json`.
2. `Import` → selecione `postman/Ressonant Local Dev.postman_environment.json`.
3. Selecione o environment **Ressonant — Local Dev** no canto superior direito.
4. Fluxo recomendado:
   - **Register** (201) → o script de teste grava `userId` na coleção.
   - **Login** (200) → o script de teste grava `accessToken` na coleção.
   - Demais requests usam `Authorization: Bearer {{accessToken}}` automaticamente (a coleção já define auth Bearer por padrão; endpoints públicos usam `noauth`).
5. Para `List Users`, os query params `skip`/`limit` vêm das variáveis `{{skip}}`/`{{limit}}`; `status_ativo` está desabilitado por padrão — habilite-o no painel de query params para filtrar.

## Como importar no Insomnia

1. `Application` → `Preferences` → `Data` → `Import Data` → `From File` (ou menu de importação equivalente na versão atual).
2. Selecione `insomnia/Ressonant API.insomnia.yaml` (formato Insomnia v4, `__export_format: 4`).
3. A coleção chega com o workspace **Ressonant API**, as pastas Health/Auth/Users e o **Base Environment** com as variáveis `base_url`, `access_token`, `user_id`, `admin_email`, `admin_senha`, `user_email`, `user_senha`, `skip`, `limit`, `status_ativo`.
4. O Insomnia usa template `{{ _.variavel }}`: as requests já referenciam `{{ _.base_url }}`, `{{ _.access_token }}` (header `Authorization`), `{{ _.user_id }}` (path) e `{{ _.skip }}`/`{{ _.limit }}` (query).
5. Fluxo: rode **Register** e **Login**, copie `id`/`access_token` da resposta e cole nas variáveis `user_id`/`access_token` do Base Environment (o Insomnia não executa scripts de teste do Postman).

## Variáveis de ambiente

| Variável (Postman) | Variável (Insomnia) | Default | Uso |
|--------------------|---------------------|---------|-----|
| `baseUrl` (+ `BASE_URL`)     | `base_url`     | `http://localhost:8000` | host da API |
| `accessToken` (+ `ACCESS_TOKEN`) | `access_token` | `""`                    | Bearer JWT (preenchido no Login) |
| `userId` (+ `USER_ID`)       | `user_id`      | `""`                    | id para `/users/{userId}` (preenchido no Register/Create) |
| `adminEmail` / `adminSenha`  | `admin_email` / `admin_senha` | `admin@example.com` / `SenhaForte123` | credenciais admin |
| `userEmail` / `userSenha`    | `user_email` / `user_senha`   | `usuario@example.com` / `SenhaForte123` | credenciais de usuário comum |
| `skip` / `limit`             | `skip` / `limit` | `0` / `50` | paginação de `List Users` |
| `status_ativo`               | `status_ativo` | `true` | filtro opcional de `List Users` |

## Scripts incluídos (Postman)

- **Nível de coleção**: pré-request que garante `baseUrl` (fallback `http://localhost:8000`) e teste global que apenas loga `método → status → tempo` (não falha a suíte).
- **Login**: teste que exige status 200 e grava `accessToken` em `pm.collectionVariables`.
- **Register** e **Create User (admin)**: testes que exigem 201/200 e gravam `userId`.
- Demais requests: `pm.response.to.have.status(...)` simples (200/201/204) — falham visivelmente no runner se a API divergir do OpenAPI.

## Não executável / fora de escopo

- Não há `pyproject.toml` de serviço, `app/`, compose ou Dockerfile aqui — de propósito.
- Não suba nada daqui; para rodar a API use o app `apps/ressonant_backend` (ex.: `make` na raiz do monorepo).
- Ao alterar rotas/schemas no backend, regenere/atualize esta coleção a partir de `apps/ressonant_backend/openapi.json`.

## Segurança

- Não commite tokens reais: os environments trazem `accessToken`/`ACCESS_TOKEN` vazios e senhas de **exemplo** apenas para desenvolvimento local.
- Não coloque segredos em variáveis de coleção versionadas.
