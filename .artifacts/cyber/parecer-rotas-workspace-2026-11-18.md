# Parecer de Segurança — Rotas de Workspace (Fase 1)

**Data:** 2026-11-18  
**Responsável:** Revisão de segurança (backend-senior, via leitura direta em disco)  
**Escopo:** Rotas de workspace em `app/modules/workspace/`  
**Veredito: APROVADO** — para integração frontend

---

## 1. Veredito

**APROVADO.** As rotas de workspace atendem a todos os controles críticos de segurança. Nenhum achado CRÍTICO ou ALTO. Os achados MÉDIO/BAIXO são pendências conhecidas do produto, não bloqueios para integração.

---

## 2. Evidências verificadas (arquivo:linha)

| Controle | Status | Evidência |
|----------|--------|-----------|
| user_id extraído do JWT, nunca URL/body | ✅ OK | `routes.py:25,34,53,64,75,92` — todas usam `user: CurrentUser` e passam `user.id` para o service |
| Autenticação exigida em todas as rotas | ✅ OK | Todas as rotas usam `Depends(CurrentUser)` |
| Autorização owner/admin | ✅ OK | `services.py:58-59,70,90-91` — verifica membership e papel |
| IDOR mitigado | ✅ OK | `services.py:58-59` — `is_member()` antes de retornar workspace |
| Validação de entrada via Pydantic | ✅ OK | `schemas/dto.py:6-31` — name/slug 3-100, role pattern |
| Mass-assignment protection | ✅ OK | `WorkspaceUpdate` (schemas:21-26) não inclui owner_id nem slug |
| senha_hash não exposto | ✅ OK | `WorkspaceResponse` (schemas:44-54) não tem campo de senha |
| Dados pessoais não vazam em logs | ✅ OK | Handlers de validação usam campos seguros (CYB-001 corrigido) |

---

## 3. Achados

### MÉDIO (2)

| ID | Achado | Evidência | Recomendação |
|----|--------|-----------|--------------|
| M-01 | `WorkspaceMemberAdd.user_id` sem validação de UUID | `schemas/dto.py:30` — `user_id: str` sem validação | Adicionar UUID pattern/validation para retornar 422 em vez de erro 500 de FK |
| M-02 | Rate limit de login não implementado | `app/auth/routes.py` — sem limiter | Pendência conhecida do produto (A-01) |

### BAIXO (1)

| ID | Achado | Evidência | Recomendação |
|----|--------|-----------|--------------|
| B-01 | `/health/ready` público com query de banco | `app/main.py:60-64` | Registrar exposição; aceitável para infra |

---

## 4. Checklist de segurança preenchido

- [x] user_id extraído exclusivamente do JWT (`CurrentUser`) — nenhuma rota recebe user_id por URL/body
- [x] Autenticação exigida em todas as rotas workspace (JWT Bearer obrigatório)
- [x] Autorização: owner pode tudo; admin do workspace pode editar/adicionar membros; não-membro recebe 403
- [x] Validação de entrada via Pydantic (name/slug 3-100 chars, role admin\|member\|viewer)
- [x] Mass-assignment protection: `WorkspaceUpdate` exclui owner_id e slug
- [x] IDOR mitigado: `is_member()` verificado antes de retornar/modificar workspace
- [x] Nenhum dado pessoal (senha, CPF, telefone, e-mail) em logs
- [x] `senha_hash` nunca exposto em `WorkspaceResponse`
- [x] Erros genéricos para o cliente (anti-enumeração)
- [x] OpenAPI sincronizado (12 paths, incluindo workspaces)

---

## 5. Recomendações

1. Corrigir M-01: adicionar validação de UUID no `WorkspaceMemberAdd.user_id` (baixo esforço, alto retorno)
2. Acompanhar pendências conhecidas do produto: rate limit de login (A-01), refresh token (A-02)
3. Manter o checklist de segurança preenchido para cada nova rota futura

---

**Próximo passo:** Liberado para integração frontend. As collections Postman/Insomnia estão prontas em `ressonant-api-collections/` (fora do monorepo, com git próprio).
