# Parecer de Segurança — Pré-Build Fase 1 (Fase 1, Passo 2)

- Data: 2026-11-18
- Escopo: backend legado (`apps/ressonant_backend`) + catálogo de contratos dos mocks (`docs/contracts/01..07`)
- Veredito: **APROVADO COM RESSALVAS** — o legado pode receber novas rotas; controles obrigatórios devem ser aplicados ANTES de cada rota nova (checklist na seção 4).

## 1. Escopo e evidências verificadas

Arquivos lidos em disco (só leitura):
- `apps/ressonant_backend/app/{auth,user,config,database,common}/**`
- `apps/ressonant_backend/migrations/versions/0001_create_users.py`
- `apps/ressonant_backend/openapi.json`, `docker-compose.yml`, `.env.example`
- `packages/errors/src/common/errors/exception_handlers.py` (+ testes)
- `docs/contracts/00-INDEX.md` + `01..06` (catálogo de contratos dos mocks)

## 2. Controles já presentes no legado (evidência arquivo:linha)

| Controle | Estado | Evidência |
|----------|--------|-----------|
| Identidade via JWT (`sub` = user_id), nunca URL/body | OK | `app/auth/deps.py:21-37`, `app/auth/tokens.py:21-34` |
| JWT HS256, `type=access`, `exp`, `iat`, rejeita tipo errado/expirado | OK | `app/auth/tokens.py:8-34`; `tests/test_auth.py:98-110` |
| Senha Argon2id; nunca exposta na resposta | OK | `app/common/security.py:9-21`; `app/user/schemas.py:100-112` |
| Anti-enumeração login (mesma resposta para usuário/senha/inativo) | OK | `app/auth/services.py:11-18` |
| RBAC: admin vs usuário; `_ensure_self_or_admin` | OK | `app/user/routes.py:22-26`; `tests/test_users.py:17-38` |
| IDOR mitigado: `get_by_id` valida UUID; rota `/{user_id}` exige self/admin | OK | `app/user/repository.py:13-18`; `app/user/routes.py:22-26` |
| Mass-assignment neutralizado: `UserUpdate` não permite senha/CPF/flags | OK | `app/user/schemas.py:74-80` |
| CYB-001 corrigido: logs sem `input`/`exception` (senha/CPF não vazam) | OK | `packages/errors/.../exception_handlers.py:20-28,60-78`; `tests/test_log_leakage.py`; `packages/errors/tests/test_exception_handlers.py:269-327` |
| Segredos obrigatórios sem default (`AUTH_SECRET`, `DATABASE_URL`, min 32 chars) | OK | `app/config/settings.py:22-43` |
| SQL parametrizado (SQLAlchemy ORM) | OK | `app/user/repository.py:20-33` |
| Validação de entrada (CPF dígitos verificadores, telefone 10/11, senha 8-128, idade 18-120) | OK | `app/user/schemas.py:14-64` |

## 3. Achados (nível / evidência / recomendação)

### ALTO — A-01: Sem rate limit de login
- Evidência: nenhuma dependência/middleware de rate limit encontrada; `POST /auth/login` aceita tentativas ilimitadas (40×401 sem 429 reportado anteriormente).
- Recomendação: adicionar rate limit (ex.: slowapi/redis) antes de expor novas rotas de auth. Pendência conhecida do AGENTS.md.

### ALTO — A-02: Sem refresh token
- Evidência: `tokens.py` só cria/decodifica access token (exp 30 min). Sem rota de refresh nem rota de revogação.
- Recomendação: definir política de refresh token antes de rotas sensíveis (workspaces, kanban, mail).

### MÉDIO — M-01: Sem headers de segurança (HSTS, CSP, X-Frame-Options, X-Content-Type-Options)
- Evidência: apenas `CORSMiddleware` em `app/main.py:39-45`. Ausente `Strict-Transport-Security`, `Content-Security-Policy`, etc.
- Recomendação: adicionar middleware de segurança antes do primeiro deploy. Baixo esforço.

### MÉDIO — M-02: `/docs` (OpenAPI UI) exposto sem proteção por ambiente
- Evidência: FastAPI expõe `/docs` por padrão; nenhuma proteção por `ENVIRONMENT`.
- Recomendação: desabilitar docs em produção/homologação ou proteger por auth.

### MÉDIO — M-03: `userId` chega como parâmetro explícito nos contratos dos mocks
- Evidência: catálogo `01..06` — todos os mocks passam `userId` explícito; regra de ouro do fluxo exige JWT-only.
- Recomendação: toda nova rota extrai o user_id do token (`CurrentUser`); rejeitar `userId` em URL/body.

### BAIXO — B-01: `readAt` tipo misto nos mocks (número/ISO/null) vs `ISODate | null` no TS
- Evidência: contrato `03-reactions-readstates-notifications.md` lacuna 1.
- Recomendação: padronizar campo de leitura como `date-time` ISO no backend.

### BAIXO — B-02: Mail aceita anexos como `dataUrl` base64 (contrato `04-mail.md`)
- Evidência: mock trata anexos como base64 embutido.
- Recomendação: no backend real, anexos devem ir para bucket privado com URL pré-assinada curta, allowlist MIME+extensão e limite de tamanho. Depende de MinIO (infra nova).

### BAIXO — B-03: Ausência global de paginação/ordenação/filtros server-side nos mocks
- Evidência: catálogo `05` (paginação stub `nextCursor=null`) e `06`.
- Recomendação: novas rotas de listagem devem trazer paginação server-side desde o início.

## 4. Checklist obrigatório ANTES de cada nova rota (deve ser preenchido pelo @cybersecurity)

- [ ] user_id extraído exclusivamente do JWT (`CurrentUser`); nenhum `user_id` em URL/body
- [ ] Autenticação exigida (`Depends(get_current_user)`) exceto rotas públicas explicitamente listadas
- [ ] Autorização por papel (admin/self) quando o recurso pertence a outro usuário
- [ ] Validação de entrada via Pydantic (tipos, comprimentos, padrões CPF/telefone/email)
- [ ] Nenhum dado pessoal (senha, CPF, telefone, e-mail) em logs (CYB-001)
- [ ] `senha_hash` nunca exposto em resposta
- [ ] Erros genéricos para o cliente (anti-enumeração)
- [ ] OpenAPI atualizado (`openapi.json`) se rota/schema mudou
- [ ] Testes de unidade/integração passando (`make test APP=backend`)
- [ ] Rate limit considerado se a rota é de auth ou de alta frequência

## 5. Veredito

**APROVADO COM RESSALVAS.** O legado atende aos controles críticos de auth/JWT/segredo/log. As ressalvas (A-01 rate limit, A-02 refresh token, M-01/M-02 headers/docs, B-01..B-03 contratos) não bloqueiam a construção da primeira rota (`GET /workspaces`), mas devem ser tratadas antes de expor rotas de auth sensíveis, mail com anexos ou qualquer rota pública.

**Próxima ação:** @backend-senior constrói `GET /workspaces` + `GET /workspaces/{id}` seguindo o checklist acima; @cybersecurity re-avalia antes da integração do frontend.
