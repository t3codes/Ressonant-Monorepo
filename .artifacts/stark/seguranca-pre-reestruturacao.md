# Relatório de Segurança — Pré-Restruturação Backend (Ressonant)

- **Data:** 2026-11-18
- **Responsável:** @foundation-stark (Arquiteto de Fundação & RH Técnico)
- **Escopo:** Backend antes da reestruturação de diretórios (`apps/ressonant_monorepo_work/apps/ressonant_backend/app/` → modularização clean architecture, sem mexer na raiz do monorepo).

## 1. Resumo executivo

Auditoria de segurança concluída sobre o backend Ressonant antes da reestruturação de diretórios. Estado geral: **POSITIVO para os controles críticos**. JWT (HS256 + exp/sub + type), Argon2id, anti-enumeração de login, validação Pydantic, proteção contra mass-assignment, gestão de segredos via env obrigatórios, mitigação de IDOR e RBAC admin estão **corretos e verificados**.

Nenhum achado CRÍTICO. As ressalvas encontradas são de **ALTO (pendências de produto/construção já mapeadas)** e **MÉDIO/BAIXO (gaps de hardening)**. A reestruturação em si **não deve degradar a segurança** se seguir as guardrails abaixo.

## 2. Lista de inconsistências encontradas

### 🔴 ALTO (2)

| ID | Inconsistência | Evidência | Recomendação |
|---|---|---|---|
| A-01 | **Sem rate limit no login.** `POST /auth/login` aceita tentativas ilimitadas → vetor de brute force. | Backend não possui slowapi/limiter/middleware; mapeado no `docs/contracts/07-legacy-inventory.md:61`. | Adicionar rate limit (ex.: slowapi/redis) antes de expor auth sensível. Pendência conhecida do produto. |
| A-02 | **Sem refresh token / revogação.** Apenas access token (exp 30 min); stateless sem rota revoke/refresh. | `app/auth/tokens.py:8-35`; contrato `07-legacy-inventory.md:62`. | Definir política de refresh/revogação antes de rotas sensíveis. Pendência conhecida. |

### 🟠 MÉDIO (3)

| ID | Inconsistência | Evidência | Recomendação |
|---|---|---|---|
| M-01 | **Sem headers de segurança** (HSTS, CSP, X-Frame-Options, X-Content-Type-Options). | Apenas `CORSMiddleware` em `app/main.py:43-49`. | Adicionar middleware de segurança antes de deploy. |
| M-02 | **`/docs` (OpenAPI) exposto sem proteção por ambiente. | FastAPI default; `app/main.py` não desabilita por `ENVIRONMENT`. | Desabilitar/ proteger docs em produção/homologação. |
| M-03 | **`userId` em URL/body nos contratos de mocks/frontend.** Backend já mitiga via self-or-admin/JWT; novas rotas devem seguir regra JWT-only. | `docs/contracts/01..07`; `app/user/routes.py:22-26` (`_ensure_self_or_admin`). | Toda nova rota extrai user_id do token (`CurrentUser`). |

### 🟡 BAIXO (2)

| ID | Inconsistência | Evidência | Recomendação |
|---|---|---|---|
| B-01 | `WorkspaceMemberAdd.user_id` sem validação de UUID no schema (pode gerar erro 500 de FK em vez de 422). | `app/workspace/schemas.py:29-31`. | Adicionar pattern/UUID validation. |
| B-02 | `/health/ready` público com query de banco (aceitável para infra, registrar exposição). | `app/main.py:60-64`. | Limitar por ambiente/segredo se necessário. |

## 3. Verificações solicitadas — status final

1. **user_id extraído do JWT em TODAS as rotas autenticadas?** ✅ **OK.** `/auth/me` via `CurrentUser`; `/workspaces/*` owner via `user.id` do token (`workspace/services.py:31-39`). Rotas `/users/{user_id}` usam path param com checagem self-or-admin (`user/routes.py:22-26`) — autorização deriva do token.
2. **Rotas sem auth que deveriam ter?** ✅ **OK.** Apenas `/auth/register`, `/auth/login`, `/health`, `/health/ready` são públicas por design.
3. **Senha em texto claro em logs? (CYB-001)** ✅ **CONFIRMADO CORRIGIDO.** `packages/errors/.../exception_handlers.py:20-28,60-78` + `tests/test_log_leakage.py` — campos seguros (`type/loc/msg`) sem `input`/`exception`.
4. **Argon2id para senhas?** ✅ **OK.** `app/common/security.py:1-21` (`$argon2id$`).
5. **JWT HS256 com exp/sub correto?** ✅ **OK.** `app/auth/tokens.py:8-35` (HS256, `exp`, `sub`, `type=access`).
6. **IDOR?** ✅ **MITIGADO.** Self-or-admin, membership e validação UUID no repository.
7. **RBAC admin vs usuário?** ✅ **OK.** `require_admin` via `interno_adm`; rotas admin-only corretamente protegidas.
8. **Segredos hardcoded?** ✅ **NÃO.** `app/config/settings.py:22-43` — obrigatórios via env, sem default, min 32 chars.
9. **Mass-assignment protection?** ✅ **OK.** `UserUpdate` exclui senha/CPF/flags; `WorkspaceUpdate` exclui `owner_id`/`slug`.
10. **Validação de entrada (CPF, telefone, email, senha)?** ✅ **OK.** CPF dígitos verificadores, telefone 10/11, email, senha 8-128, idade 18-120. Resalvas menores (B-01).

## 4. Recomendações antes de reestruturar

- **Preservar `app/common/` e o pacote namespace `common`** durante a reestruturação — mover a raiz `app/` pode quebrar imports como `from common.errors import ...` (risco identificado: namespace package `common-*` do workspace).
- Preservar prefixos de rota, contratos OpenAPI (`openapi.json`) e camada routes→services→repository→models.
- Não introduzir `async` sem decisão explícita (execução síncrona atual).
- Rodar antes/depois: `make test APP=backend`, `make -C apps/ressonant_backend export-openapi`, `make check`.

## 5. O que é seguro para manter como está

JWT, Argon2id, anti-enumeração, validação, mass-assignment, segredos, IDOR, RBAC e CYB-001 **devem permanecer inalterados** durante a reestruturação.

---

**Arquivos lidos:** todos os solicitados existem (auth/, user/, workspace/, common/, config/, database/, main.py, tests/). Extras lidos para contexto: `auth/schemas.py`, `database/engine.py`, `workspace/deps.py`, `workspace/repository.py`, `workspace/schemas.py`, `scripts/create_admin.py`, `packages/errors/**`, `packages/logs/**`, `tests/**`, contratos `docs/contracts/01..07`.

**Pendências conhecidas (não bloqueiam auditoria):** rate limit (A-01), refresh token (A-02), headers (M-01), docs exposure (M-02).
