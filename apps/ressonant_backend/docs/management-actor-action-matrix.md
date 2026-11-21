# Matriz Ator × Ação — Gestão do Workspace (Fase 0)

> Artefato P0. Fonte de verdade de autorização: backend. Frontend apenas reflete capabilities.
> Estado conferido em 2026-11-21 (Fase 0, O0): as rotas abaixo existem em `app/modules/workspace_management/entrypoints/routes.py` e estão no `openapi.json`.
> O prefixo real é `/workspaces/{workspace_id}/management` — um caminho `/management/...` sozinho **não existe**.

## Níveis (implementados)
- **MG none/read/modify/grant** = `workspace_management_grants.level`; `none` quando não há grant ativo.
- **Implícito**: owner do workspace e `users.interno_adm` resolvem para `grant` em `resolve_access()`.
- **R9 (implementado)**: somente owner/interno_adm concede/revoga nível `grant`; titular de `grant` concede/revoga até `modify`.
- **R10 (implementado)**: `interno_adm` mutando fora de membership operacional exige `reason` + auditoria `break_glass`.
- **Planejado — Fase 0/1 (não implementado)**: Dono da Empresa, Admin da organização e Billing Owner (`organizations` / `organization_members`) e `GET /me/context` (D7). Billing Owner não terá grants de gestão.

## Matriz — implementado no backend (Fase 0, O0)

Prefixo omitido nas linhas abaixo: `/workspaces/{workspace_id}/management`.

| Ação | owner | interno_adm | admin ws sem MG | member MG read | member MG modify | member MG grant | viewer/member sem MG | usuário revogado |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `GET .../access/me` | 200 grant | 200 grant | 200 none | 200 read | 200 modify | 200 grant | 200 none | 200 none/401 conforme sessão |
| `GET .../grants` | 200 | 200 | 403 | 200 | 200 | 200 | 403 | 403/401 |
| `POST .../grants` (read/modify) | 201 | 201 | 403 | 403 | 403 | 201 | 403 | 403/401 |
| `POST .../grants` (grant) | 201 | 201 | 403 | 403 | 403 | 403 R9 | 403 | 403/401 |
| `DELETE .../grants/{target_user_id}` (read/modify) | 204 | 204 | 403 | 403 | 403 | 204 | 403 | 403/401 |
| `DELETE .../grants/{target_user_id}` (grant) | 204 | 204 | 403 | 403 | 403 | 403 R9 | 403 | 403/401 |
| `GET .../people` | 200 | 200 | 403 | 200 | 200 | 200 | 403 | 403/401 |
| `GET .../teams` | 200 | 200 | 403 | 200 | 200 | 200 | 403 | 403/401 |
| `GET .../blocked-cards` | 200 | 200 | 403 | 200 | 200 | 200 | 403 | 403/401 |
| `GET .../audit-events` | 200 | 200 | 403 | 200 | 200 | 200 | 403 | 403/401 |
| Ação de domínio via admin (ex. unblock) | MG+domínio | MG+domínio | 403 MG | 403 modify | MG+domínio | MG+domínio | 403 MG | 403/401 |

`access/me` devolve `level`, `permission_version` e as 14 `capabilities` (`management_read`, `management_modify`, `management_grant`, `teams_create/update/soft_delete/hard_delete`, `members_manage`, `columns_manage`, `blocked_cards_read/unblock`, `audit_read`, `settings_manage`, `grants_manage`). As quatro listas administrativas acima exigem `require_read`; nenhuma escreve em `audit_events`.

## Contratos de erro implementados
- Sem permissão de gestão: `403`, `error_code=MANAGEMENT_ACCESS_DENIED`, `error_layer=management`, `required_capability=management.read|management.modify|management.grant`.
- Escalada R9: `403`, `error_code=MANAGEMENT_GRANT_ESCALATION_DENIED`, `error_layer=management`, `required_capability=management.grant.grant`.
- Nível inválido: `409`, `error_code=MANAGEMENT_GRANT_INVALID_LEVEL`.
- Alvo fora do workspace: `404`, `error_code=WORKSPACE_MEMBER_NOT_FOUND`; grant inexistente na revogação: `404`, `error_code=MANAGEMENT_GRANT_NOT_FOUND`.
- Break-glass sem reason: `403`, `error_code=BREAK_GLASS_REASON_REQUIRED`, `error_layer=management`, `required_capability=management.break_glass_reason`.
- Domínio bloqueia: `403`, `error_layer=domain`, `error_code`/policy específica.

## Cobertura de testes (`tests/test_workspace_management.py`)
- [x] `access/me` por perfil (owner, `interno_adm`, `none`/`read`/`modify`/`grant`)
- [x] grants create/update/revoke + R9 (escalada `grant` negada)
- [x] revogação invalida acesso efetivo
- [x] `interno_adm` break-glass: sem `reason` → 403; com `reason` → evento `internal_admin` auditado
- [ ] endpoint admin não bypassa policy de domínio — **Planejado — Fase 3** (gate P3-7); as quatro listas acima são somente leitura e não têm testes dedicados nesta suíte
- [ ] auditoria append-only por privilégio de banco — **Planejado — Fase 0 (O3, migration `0017`)**: hoje `audit_events` é append-only por repositório/service, sem `UPDATE`/`DELETE` bloqueados no banco
- [ ] concorrência 409 (quando aplicável) — sem cobertura

## Planejado — Fase 0/1 (não implementado)
- `GET /me/context` (D7) e o consumo frontend das capabilities: hoje só existe `GET /auth/me` e o frontend ainda não consome `access/me` como fonte única.
- `organizations`, `organization_members`, Dono da Empresa, Admin da organização e Billing Owner: papéis hierárquicos ainda não existem no backend.
- `plans`/`subscriptions`, seats, trial e delegação/transferência de propriedade: ainda não existem.
- Promoção a `admin` de domínio sem concessão de grant: ainda sem papel de domínio `admin` na gestão; regra prevista para a Fase 3.
