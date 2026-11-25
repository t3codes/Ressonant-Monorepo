# 3. Admin de Plataforma, Catálogo de Planos e Invalidação de Sessão

- **Status**: Proposto (Lote 4 — sujeito aos gates do relatório `ARQ-REVIEW-BACKOFFICE-2026-11-25.md`)
- **Data**: 2026-11-25
- **Relacionada**: [ADR 0001 — snake_case como contrato HTTP](0001-http-snake-case.md); `docs/guides/app-structure.md`
- **Snapshot do código**: 2026-11-25T17:53:30Z. O working tree estava com edições paralelas de outros agentes; as linhas citadas descrevem o que foi lido nesse instante.

## Contexto

A plataforma precisa de uma fronteira explícita entre **admin da plataforma** (poder global, fora de qualquer tenant) e **dono de organização/workspace** (poder escopado a uma tupla de membership). Hoje os dois poderes usam sinais que se parecem, mas não são o mesmo:

| Fato | Evidência |
|---|---|
| `interno_adm` é um booleano global em `users`, sem escopo de tenant | `apps/ressonant_backend/app/modules/user/domain/models.py:29` |
| Dono da empresa é uma linha de `organization_members` com `role='owner'` | `apps/ressonant_backend/app/modules/auth/usecases/registration.py:328-335` |
| Dono do workspace é `workspaces.owner_id` | `apps/ressonant_backend/app/modules/workspace/domain/models.py:18-20` |
| `resolve_access` trata `owner_id`, `interno_adm` e `organization_members.role` como acesso inerente | `apps/ressonant_backend/app/modules/workspace_management/dataproviders/repository.py:41-54` |
| Break-glass de `interno_adm` fora de membership já exige `reason` em billing, organização e gestão | `apps/ressonant_backend/app/modules/billing/usecases/services.py:113-126`; `apps/ressonant_backend/app/modules/organization/usecases/services.py:191-200`; `apps/ressonant_backend/app/modules/workspace_management/usecases/services.py:205-217` |
| `plans` já tem colunas novas e legadas convivendo | `apps/ressonant_backend/app/modules/billing/domain/models.py:16-71` |
| Contrato de cadastro aceita só três códigos de plano | `apps/ressonant_backend/app/modules/auth/schemas/dto.py:111` |
| Claim de versão de permissão e guarda no `get_current_user` já foram introduzidos em paralelo | `apps/ressonant_backend/app/modules/auth/usecases/tokens.py:30,48`; `apps/ressonant_backend/app/modules/auth/deps.py:46-49` |
| ORM aceita `scope='system'`, mas o `CHECK` do banco ainda não | `apps/ressonant_backend/app/modules/workspace_management/domain/models.py:117-120` vs `apps/ressonant_backend/migrations/versions/0017_generalize_audit_events_and_enforce_append_only.py:92` |

Sem uma decisão escrita, cada rota nova e cada seed resolve essas ambiguidades por conta própria. Esta ADR fixa a fronteira.

## Decisão

### (i) `interno_adm` é poder global; `owner` é tupla de membership

Nós mantemos **dois eixos distintos e não conversíveis**:

- `users.interno_adm` é o poder da plataforma. Ele autoriza somente operações de plataforma (`/admin/*`, catálogo global, bootstrap, configurações globais). Não é derivado de membership e não é concedido por transferência de propriedade.
- `organization_members.role='owner'` e `workspaces.owner_id` são poderes de tenant. Eles autorizam operação dentro da organização/workspace correspondente.

Quando `interno_adm` atua fora de membership operacional, a regra de break-glass existente se aplica: `reason` obrigatório e evento com `actor_type='internal_admin'`. Nós **não** criamos um papel de "superowner" nem fazemos `interno_adm` implicar linha em `organization_members`.

Múltiplos superusers são permitidos: não há restrição de unicidade sobre `interno_adm`, e o bootstrap idempotente promove um usuário existente em vez de criar outro (`apps/ressonant_backend/app/scripts/create_admin.py:45-61`).

### (ii) Guarda do último administrador

A guarda `LAST_ADMIN_PROTECTED` vive no **service**, nunca somente na rota, e usa `ConflictException` → **409** (`apps/ressonant_backend/app/common/exceptions.py:5-6`). A condição protegida é: alvo é admin **ativo**, é o **único** admin ativo, e a operação o revoga ou desativa.

A checagem é feita sob bloqueio (`FOR UPDATE`) na mesma transação da mutação, e a auditoria `scope='system'` entra no **mesmo commit**. A contagem considera `status_ativo=True`; um admin inativo não conta como admin sobrevivente.

### (iii) Invalidação de sessão via `permission_version` no JWT

O access token carrega a claim `perm_version`, espelhando `users.permission_version` (`apps/ressonant_backend/app/modules/auth/usecases/tokens.py:16-32`). `get_current_user` compara a claim com o valor persistido e rejeita com `401 INVALID_TOKEN` quando divergem (`apps/ressonant_backend/app/modules/auth/deps.py:40-49`).

Tokens sem a claim são **rejeitados** (fail closed); não há fallback para versão 1, porque fallback permitiria que uma sessão antiga sobrevivesse a uma revogação (`apps/ressonant_backend/app/modules/auth/usecases/tokens.py:35-60`).

Custo e limitações que aceitamos:

- Não há consulta extra ao banco: `get_current_user` já carregava o `User` antes da claim. O custo é uma comparação de inteiro por requisição.
- Um bump invalida **todas** as sessões ativas daquele usuário. Não há refresh token implantado no repo (`AGENTS.md`, linha 24), então o usuário faz login novamente; não prometemos renovação transparente.
- `users.permission_version` e `workspaces.management_permission_version` são **versões diferentes com propósitos diferentes**. A primeira invalida sessão; a segunda alimenta capabilities de gestão e o `/me/context.permission_version` hoje (`apps/ressonant_backend/app/modules/context/usecases/services.py:93-95`). Nós não as unificamos nesta decisão e nunca usamos uma no lugar da outra sem card próprio.
- O canal WebSocket autentica por `decode_access_token` (`apps/ressonant_backend/app/modules/chat/entrypoints/websocket.py:295-301`). Como `decode_access_token` agora delega a `decode_access_claims`, a claim passa a ser exigida também no WS; a **comparação** com a versão persistida, porém, precisa ser verificada no fluxo de conexão antes de declarar invalidação completa.

### (iv) Catálogo dinâmico de planos com compatibilidade legada

**Decisão: opção A do pré-parecer CYB-005 — seed insere `trial_default` e mantém/insere `inicial`, `equipe` e `empresa`. Contrato HTTP inalterado.**

Justificativa: `RegistrationCreate.plano_id` é `Literal["inicial","equipe","empresa"]` (`apps/ressonant_backend/app/modules/auth/schemas/dto.py:111`), o registro usa esse valor como `plan_code` (`apps/ressonant_backend/app/modules/auth/usecases/registration.py:337-339`) e `_resolve_plan` devolve `PLAN_NOT_FOUND` se o código não existe (`apps/ressonant_backend/app/modules/billing/usecases/services.py:135-139`). Um seed contendo apenas `trial_default` **não destrava cadastro**: a requisição é rejeitada pelo schema antes de chegar ao service, e os três códigos legados continuam protegidos por `_PROTECTED_PLAN_CODES` (`apps/ressonant_backend/app/modules/billing/usecases/services.py:29,437,469,486`). A ADR 0001 determina que contrato já publicado não se converte sem card próprio.

Nós preservamos as colunas legadas de `plans` (`price_cents`, `currency`, `seat_limit`, `overage_cents_per_seat`, `trial_days`, `active`) porque os serviços atuais ainda as leem; as colunas novas (`billing_cycle`, `base_price_cents`, `price_per_seat_cents`, `included_seats`, `limits`, `is_public`, `is_active`) são aditivas (`apps/ressonant_backend/app/modules/billing/domain/models.py:24-56`).

`system_settings` **não** é a fonte do plano inicial nesta decisão. Ela guarda configuração de plataforma; o cadastro continua determinístico e independente de leitura de config.

### (v) Escopo `system` na auditoria

Eventos de plataforma usam `AuditEvent(scope='system')` com `organization_id=None`, `workspace_id=None`, `actor_type='internal_admin'` quando há operador e `'system'` quando não há, `actor_user_id` preenchido quando aplicável, `permission_version` do ator, `request_id` quando disponível e `result` explícito.

A migration `6b31f6ec3d46_platform_admin_schema.py` foi **criada e revisada** para ampliar o `CHECK`: `0017` fixava `scope IN ('organization','workspace','card')` (`apps/ressonant_backend/migrations/versions/0017_generalize_audit_events_and_enforce_append_only.py:92`), e a migration nova faz drop/recreate de `ck_audit_events_scope` com `scope IN ('organization','workspace','card','system')` (`apps/ressonant_backend/migrations/versions/6b31f6ec3d46_platform_admin_schema.py:18,93-95`), sem `UPDATE`/`DELETE`, preservando eventos existentes. O downgrade **bloqueia** se houver evento `scope='system'`, em vez de falsificar a auditoria convertendo o escopo (`:6-8,139-148`).

**A aplicação da migration ainda está pendente dos gates.** Até `migrate/apply` ser executado e verificado, escrita `scope='system'` falha no Postgres.

Append-only permanece. Nunca gravar senha, hash, token, segredo ou dado pessoal em `before`/`after`/`metadata`.

### (vi) Seed de produção idempotente

Um único entrypoint de bootstrap (`make prod-init APP=backend`) executa, **nesta ordem determinada pelo Dono**: `migrate/apply` → `migrate/create-admin` → `seed-prod-catalog` (`apps/ressonant_backend/Makefile:46,49`; o target de seed ainda precisa ser criado).

A ordem é do Dono. Nesta versão as três etapas são idempotentes e **não dependem entre si**: `migrate/apply` é seguro por ser versionado; `migrate/create-admin` busca por e-mail e valida CPF; o seed usa `ON CONFLICT (code) DO NOTHING`. A única precedência técnica necessária é a da migration em relação às outras duas, porque ela cria `users.permission_version`, `plans` e `system_settings`.

- admin: busca por e-mail, valida CPF, promove `interno_adm=True` e `status_ativo=True` se já existir, sem trocar `senha_hash`;
- catálogo: `ON CONFLICT (code) DO NOTHING`, sem `TRUNCATE`, sem `DELETE`, sem sobrescrever preço ou `active` de plano existente;
- configuração: `ADMIN_*` lidas de env, tipadas e fora de `repr` (`apps/ressonant_backend/app/config/settings.py:23-32,93-97`); ausência em produção é erro, não default.

**Aviso ao `@backend-senior`:** a troca da ordem em relação ao rascunho anterior não tem impacto técnico bloqueante identificado. O seed de catálogo não lê `users` nem escreve `updated_by`, então executá-lo depois do admin é neutro; se o seed falhar, o admin já criado permanece, o que é aceitável porque a reexecução é idempotente. Não inverter `migrate/apply`: as duas outras etapas dependem do schema criado por ela.

### (vii) Propriedade de workspace (CYB-009)

A **fonte de verdade** da propriedade do workspace é `workspaces.owner_id`. `workspace_members.role` é projeção e deve ser sincronizada na mesma transação. A transferência não altera `users.interno_adm`.

Hoje `transfer_owner` atualiza `owner_id` mas grava `new_owner_member.role = "admin"` (`apps/ressonant_backend/app/modules/workspace/usecases/services.py:251-277`), e `/me/context` devolve `role=member.role` (`apps/ressonant_backend/app/modules/context/usecases/services.py:129-149`). Resultado: o novo dono aparece como `admin`. A decisão é gravar `role='owner'` para o novo dono, rebaixar o antigo para `admin` e bump de `management_permission_version` no mesmo commit, com teste de regressão cobrindo a transferência.

`owner` continua significando "dono do workspace" nas capabilities; **não** significa "admin da plataforma". Para evitar confusão futura, qualquer campo que represente poder global deve ser explícito (`is_platform_admin`), nunca reaproveitar `role`.

## Alternativas rejeitadas

| Alternativa | Motivo da rejeição |
|---|---|
| **B — ampliar `Literal` e mapear `trial_default`** | Muda contrato já publicado e exige coordenação com clientes; a ADR 0001 não autoriza isso em review. |
| **C — configurar código do plano inicial via `system_settings`** | Introduz leitura de config no cadastro sem necessidade; além disso não resolve sozinha a compatibilidade dos três códigos legados já validados pelo schema. Pode ser evolução futura, não decisão deste lote. |
| Substituir `interno_adm` por tabela global de papéis | Mudança estrutural sem consumo real; a regra de simplicidade da `AGENTS.md` §5 a desaconselha. |
| Remover colunas legadas de `plans` | Quebra os serviços de billing atuais que ainda as leem (`apps/ressonant_backend/app/modules/billing/domain/models.py:48-55`). |
| Invalidar sessão por blacklist em Redis | Redis é `Planejado — Fase 4`; não há infraestrutura implantada para sustentar a garantia. |
| Unificar `permission_version` de usuário e de workspace | São eixos diferentes (sessão vs. capability de gestão); unificar alteraria o contrato do `/me/context`. |

## Consequências

1. Rotas `/admin/*` passam a depender de uma única guarda de plataforma; reutilizar `require_admin` de tenant é fora desta decisão.
2. A guarda do último admin e o bump de `permission_version` precisam estar no service, sob transação, com evento `scope='system'` no mesmo commit.
3. Seed de produção precisa ser executado por target único e idempotente; nenhuma etapa pode destruir dados existentes.
4. A migration `6b31f6ec3d46` já amplia o `CHECK` de `audit_events.scope` e bloqueia downgrade com eventos `system`; a **aplicação** segue pendente dos gates — sem ela, a auditoria de plataforma não grava.
5. Transferência de propriedade passa a ter teste de regressão; `/me/context` reflete `owner` para o novo dono sem conceder poder de plataforma.
6. **Impacto operacional aceito:** clientes com token emitido antes da claim `perm_version` são **rejeitados no deploy** (fail closed, sem fallback para versão 1) e precisam fazer login novamente. Isso é aceito explicitamente em troca de invalidação confiável.
7. `make prod-init APP=backend` executa `migrate/apply` → `migrate/create-admin` → `seed-prod-catalog`, ordem definida pelo Dono; nenhuma das três etapas destrói estado existente na reexecução.
8. Dívida registrada: `extra='forbid'` nos schemas das rotas `/admin/*` e checagem da versão no handshake WebSocket precisam ser confirmadas nos gates.
