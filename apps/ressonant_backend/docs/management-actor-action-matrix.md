# Matriz Ator × Ação — Gestão do Workspace (Fase 0)

> Artefato P0. Fonte de verdade de autorização: backend. Frontend apenas reflete capabilities.
> Estado conferido em 2026-11-21 (Fase 0, O0–O4; gates P0-4/P0-5/P0-6): rotas de gestão em `app/modules/workspace_management/entrypoints/routes.py`, de billing em `app/modules/billing/entrypoints/routes.py` e bootstrap em `app/modules/context/entrypoints/routes.py`, todas publicadas no `openapi.json` (63 paths, SHA `27d9a65d8d2e43446dc9235c0ebcd6cdea17cba575ccf6f3f8ee740b7843b6f4`). D1 e D7 estão **Entregues — Fase 0** (P0-2/P0-6); ver `docs/contracts/00-INDEX.md`.
> O prefixo real é `/workspaces/{workspace_id}/management` — um caminho `/management/...` sozinho **não existe**.

## Níveis e papéis (Entregue — Fase 0, P0-4)

- **MG none/read/modify/grant** = `workspace_management_grants.level`; `none` quando não há grant ativo.
- **Implícito**: owner do workspace, Dono da Empresa (`organization_members.role=owner`) e `users.interno_adm` resolvem para `grant` em `resolve_access()`. Admin da org e Dono/Admin de workspace também resolvem para `grant`, mas não escalam (R9). Billing Owner não administra gestão de workspace (separação de poderes); sem grant ele fica em `none`, e com grant o nível é reduzido a `read`.
- **R9 (implementado)**: somente Dono da Empresa (por membership) ou `interno_adm` concede/revoga nível `grant`. Admin da org, Dono/Admin de workspace e titular de `grant` concedem/revogam até `modify`. Escalada → `403 MANAGEMENT_GRANT_ESCALATION_DENIED`, sem linha nova e sem evento.
- **R10 (implementado)**: `interno_adm` mutando fora de membership operacional exige `reason` (campo `reason` no body da API de grants; header `x-break-glass-reason` no billing). Sem ele → `403 BREAK_GLASS_REASON_REQUIRED` e nenhum evento; com ele → evento `break_glass` com `actor_type=internal_admin` e `metadata.reason`.
- **D5 (decisão fechada)**: viewer sem vínculo não recebe deep-link a recursos de outrem; a API não distingue `403` de `404` para não enumerar. O estado “Sem acesso a esta equipe” e a checagem de boards/cards são **Planejado — Fase 2 (P2-1)**.
- **Billing (implementado)**: `owner` e `billing_owner` da org veem e alteram billing; os demais papéis não. Respostas com `provider=stub` e `simulation=true` — sem rede, sem chave e sem cobrança real (D3).
- **Estrutura entregue**: tabelas `organizations`/`organization_members`/`invitations` (migration `0015`) e `plans`/`subscriptions` (migration `0016`). `GET /me/context` (D7) devolve as capacidades agregadas e é consumido no bootstrap do frontend. `audit_events` é append-only no Postgres por `REVOKE` + trigger (migration `0017`, P0-5).

## Matriz de gestão — implementado no backend (Fase 0, O0)

Prefixo omitido nas linhas abaixo: `/workspaces/{workspace_id}/management`.

| Ação | Dono Empresa (`owner` org) | interno_adm | Admin org | Dono/Admin ws | MG grant | MG modify | MG read | Billing Owner | sem vínculo / revogado |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `GET .../access/me` | 200 grant | 200 grant | 200 grant | 200 grant | 200 grant | 200 modify | 200 read | 200 none | 200 none/401 conforme sessão |
| `GET .../grants`, `/people`, `/teams`, `/blocked-cards`, `/audit-events` | 200 | 200 | 200 | 200 | 200 | 200 | 200 | 403 (200 read se tiver grant) | 403/401 |
| `POST .../grants` (read/modify) | 201 | 201 | 201 | 201 | 201 | 403 | 403 | 403 | 403/401 |
| `POST .../grants` (grant) | 201 | 201 | 403 R9 | 403 R9 | 403 R9 | 403 | 403 | 403 | 403/401 |
| `DELETE .../grants/{target_user_id}` (read/modify) | 204 | 204 | 204 | 204 | 204 | 403 | 403 | 403 | 403/401 |
| `DELETE .../grants/{target_user_id}` (grant) | 204 | 204 | 403 R9 | 403 R9 | 403 R9 | 403 | 403 | 403 | 403/401 |
| Ação de domínio via admin (ex. unblock) | MG+domínio | MG+domínio + `reason` | MG+domínio | MG+domínio | MG+domínio | MG+domínio (sem grant) | 403 MG | 403 | 403/401 |

Toda mutação de `interno_adm` fora de membership nas linhas acima exige `reason`; o ponto de verificação está no service, não na UI. `access/me` devolve `level`, `permission_version` e as 14 `capabilities` (`management_read`, `management_modify`, `management_grant`, `teams_create/update/soft_delete/hard_delete`, `members_manage`, `columns_manage`, `blocked_cards_read/unblock`, `audit_read`, `settings_manage`, `grants_manage`). As listas administrativas exigem `require_read`; nenhuma escreve em `audit_events`.

## Matriz de cinco eixos — billing e domínio (testada em `tests/test_billing_rbac.py`)

| Papel (`organization_members.role` / eixo) | Ver billing | Alterar plano/seats | Conceder `grant` | Conceder até `modify` | Mutar card |
|---|---:|---:|---:|---:|---|
| Dono da Empresa (`owner` org) | 200 | 200 | 201 | 201 | conforme domínio |
| Billing Owner (delegação do Dono) | 200 | 200 | 403 | 403 | 403 |
| Admin da organização (`admin` org) | 403 | 403 | 403 R9 | 201 | conforme domínio |
| Dono/Admin de workspace | 403 | 403 | 403 R9 | 201 | conforme domínio |
| Grant `grant` | 403 | 403 | 403 R9 | 201 | conforme domínio |
| Grant `modify` / `read` | 403 | 403 | 403 | 403 | conforme domínio (`read` só lê gestão) |
| `interno_adm` (fora de membership, com `reason`) | 200 | 200 | 201 | 201 | conforme domínio |
| Viewer sem vínculo (D5) | 403 | 403 | 403 | 403 | 403; deep-link negado (`404` na UI; API `403`/`404` indistinguíveis) |

Promover a `admin` de domínio **não** concede grant de gestão. As capabilities da UI vêm do bootstrap; o servidor é a última barreira.

## Billing entregue — Fase 0 (P0-4)

Prefixo: `/organizations/{organization_id}`.

| Método | Rota | Efeito |
|---|---|---|
| `GET` | `/billing` | plano, `seats_used`, seats comprados e assinatura; `provider=stub`, `simulation=true` |
| `PATCH` | `/billing` | altera `plan_code`/`seats_purchased` com checagem de `seat_limit` antes do commit |
| `POST` | `/billing/subscription` | cria assinatura `trialing` via gateway stub, sem requisição externa |
| `PATCH` | `/billing/subscription/status` | transições `trialing→active→past_due→canceled` (ou `409 INVALID_SUBSCRIPTION_TRANSITION`) |

Catálogo `inicial`/`equipe`/`empresa`: preços propostos, seats `3`/`15`/ilimitado, 14 dias de trial, uplift quando aplicável (D3 — não é valor contratado). Cada mutação grava `AuditEvent` com `scope=organization`, `actor_role`, `permission_version`, `request_id`, `result=success` e `before`/`after` redacionados no mesmo commit.

## Contratos de erro implementados

- Sem permissão de gestão: `403`, `error_code=MANAGEMENT_ACCESS_DENIED`, `error_layer=management`, `required_capability=management.read|management.modify|management.grant`.
- Escalada R9: `403`, `error_code=MANAGEMENT_GRANT_ESCALATION_DENIED`, `error_layer=management`, `required_capability=management.grant.grant`.
- Nível inválido: `409`, `error_code=MANAGEMENT_GRANT_INVALID_LEVEL`.
- Alvo fora do workspace: `404`, `error_code=WORKSPACE_MEMBER_NOT_FOUND`; grant inexistente na revogação: `404`, `error_code=MANAGEMENT_GRANT_NOT_FOUND`.
- Break-glass sem reason: `403`, `error_code=BREAK_GLASS_REASON_REQUIRED`, `error_layer=management`, `required_capability=management.break_glass_reason`.
- Sem acesso a billing: `403`, `error_code=BILLING_ACCESS_DENIED`, `error_layer=billing`, `required_capability=billing.view|billing.manage`; sem reason no break-glass de billing: `403 BREAK_GLASS_REASON_REQUIRED`, `required_capability=billing.break_glass_reason`.
- Billing/domínio: `404 ORGANIZATION_NOT_FOUND|PLAN_NOT_FOUND|SUBSCRIPTION_NOT_FOUND`; `409 SEAT_LIMIT_EXCEEDED|SUBSCRIPTION_ALREADY_ACTIVE|BILLING_INTENT_REJECTED|INVALID_SUBSCRIPTION_TRANSITION`; `422` para campo extra ou inválido (`extra="forbid"`). Sem vínculo, `403`/`404` são indistinguíveis para não enumerar (D5).
- Domínio bloqueia: `403`, `error_layer=domain`, `error_code`/policy específica.

## Cobertura de testes (Fase 0 — `make check`: exit 0; backend `154 passed, 6 skipped`)

- [x] `tests/test_workspace_management.py`: `access/me` por perfil (owner, `interno_adm`, `none`/`read`/`modify`/`grant`), grants create/update/revoke + R9, revogação invalida acesso efetivo, `interno_adm` break-glass sem `reason` → 403 e com `reason` → evento auditado.
- [x] `tests/test_billing_rbac.py`: matriz de cinco eixos parametrizada (9 perfis × ver/alterar billing, conceder `grant`/`modify`, mutar card), R9 sem evento na falha, R10 com `reason` auditado, `SEAT_LIMIT_EXCEEDED` sem órfãos, ciclo de assinatura sem socket, auditoria com `scope`/`actor_role`/`request_id` e contrato publicado no OpenAPI.
- [x] `tests/test_audit_events.py`: roundtrip de evento com `scope=card`, derivação de `actor_role`, redação de campos sensíveis e rejeição de `UPDATE`/`DELETE` diretos no Postgres (skip fora Postgres).
- [x] `tests/test_context.py`: shape de `/me/context` (7 chaves), `member_ids`/`teams` lidos do banco, capabilities por papel, isolamento IDOR, assinatura ativa exposta e rota autenticada sem query parameters.
- [x] `tests/test_openapi_sync.py`: `openapi.json` versionado sincronizado com `app.openapi()` (63 paths, SHA `27d9a65d8d2e43446dc9235c0ebcd6cdea17cba575ccf6f3f8ee740b7843b6f4`).
- [x] auditoria append-only por privilégio de banco — **Entregue — Fase 0 (O3, P0-5)**: a migration `0017` aplica `REVOKE UPDATE, DELETE ON TABLE audit_events` ao papel da aplicação e cria o trigger `audit_events_append_only` no Postgres; a mutação de domínio grava o evento no mesmo commit. A proteção é do banco, não apenas do service.
- [ ] endpoint admin não bypassa policy de domínio — **Planejado — Fase 3 (P3-7)**; as listas administrativas acima são somente leitura e não têm testes dedicados nesta suíte.
- [ ] concorrência de chaves legíveis e conflito de versão — **Planejado — Fase 2 (P2-2/P2-3)**; sem cobertura nesta suíte.

## Planejado — fases seguintes (fora do O0)

- Consumo das 8 abas de gestão a partir de `access/me` no frontend — **Planejado — Fase 3 (P3-1)**; o bootstrap `/me/context` (D7) já entrega capacidades agregadas e é consumido uma vez por sessão.
- Delegação de Billing Owner/Admin e transferência atômica de propriedade — **Planejado — Fase 1 (P1-5)**. As tabelas `plans` e `subscriptions`, os seats, o trial e o gateway stub já foram entregues.
- Promoção a `admin` de domínio sem concessão de grant — **Planejado — Fase 3 (P3-1)**.
- `GET /auth/bootstrap` — fora de escopo por D7; não implementar.
