# Matriz Ator × Ação — Gestão do Workspace (Fase 0)

> Artefato P0. Fonte de verdade de autorização: backend. Frontend apenas reflete capabilities.

## Níveis
- **MG none/read/modify/grant** = grant de gestão do workspace.
- **Implícito**: owner do workspace e `interno_adm` = `grant`.
- **R9**: somente owner/interno_adm concede/revoga nível `grant`; `grant` concede/revoga até `modify`.
- **R10**: `interno_adm` mutando fora de membership operacional exige `reason` + auditoria `break_glass`.

## Matriz (MVP/Fase 0-1)

| Ação | owner | interno_adm | admin ws sem MG | member MG read | member MG modify | member MG grant | viewer/member sem MG | usuário revogado |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `GET /management/access/me` | 200 grant | 200 grant | 200 none | 200 read | 200 modify | 200 grant | 200 none | 200 none/401 conforme sessão |
| `GET /management/grants` | 200 | 200 | 403 MG_DENIED | 200 | 200 | 200 | 403 MG_DENIED | 403/401 |
| `POST /management/grants` (read/modify) | 201 | 201 | 403 | 403 | 403 | 201 | 403 | 403/401 |
| `POST /management/grants` (grant) | 201 | 201 | 403 | 403 | 403 | 403 R9 | 403 | 403/401 |
| `DELETE /management/grants/{user}` (read/modify) | 204 | 204 | 403 | 403 | 403 | 204 | 403 | 403/401 |
| `DELETE /management/grants/{user}` (grant) | 204 | 204 | 403 | 403 | 403 | 403 R9 | 403 | 403/401 |
| Ação de domínio via admin (ex. unblock) | MG+domínio | MG+domínio | 403 MG | 403 modify | MG+domínio | MG+domínio | 403 MG | 403/401 |

## Contratos de erro esperados
- Sem permissão de gestão: `403`, `error_code=MANAGEMENT_ACCESS_DENIED`, `error_layer=management`, `required_capability=management.*`.
- Escalada R9: `403`, `error_code=MANAGEMENT_GRANT_ESCALATION_DENIED`, `error_layer=management`.
- Break-glass sem reason: `403`, `error_code=BREAK_GLASS_REASON_REQUIRED`, `error_layer=management`.
- Domínio bloqueia: `403`, `error_layer=domain`, `error_code`/policy específica.

## Cobertura de testes
- [ ] `access/me` por perfil
- [ ] grants CRUD + R9
- [ ] revogação invalida acesso efetivo
- [ ] interno_adm break-glass reason
- [ ] endpoint admin não bypassa policy de domínio
- [ ] auditoria append-only para mutações
- [ ] concorrência 409 (quando aplicável)
