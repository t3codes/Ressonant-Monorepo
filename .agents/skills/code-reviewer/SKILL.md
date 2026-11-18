---
name: code-reviewer
description: Revisão rigorosa de código e arquitetura do monorepo Ressonant antes de commit ou PR. Use ao revisar um diff, uma branch, um arquivo ou um PR; ao pedirem "revise", "code review", "está pronto para commit?" ou ao validar uma mudança contra ADRs, check-structure, hooks, tipagem, segurança, transações, N+1 e bloqueio do event loop. Somente leitura: relata achados com arquivo:linha e correção, não edita.
metadata:
  scope: monorepo
  language: pt-BR
---

# code-reviewer

Revise **o diff pedido**, não o repositório inteiro. Código legado fora do diff não é achado.

## Processo

1. Delimite o escopo: `git status`, `git diff` (ou o PR/branch indicado). Leia os arquivos tocados **inteiros**, não só os trechos do diff.
2. Rode as verificações automáticas relevantes **antes** de opinar (somente leitura, sem autofix):
   ```bash
   make lint-check && make format-check      # ruff
   make test APP=backend                     # unitários
   make -C apps/ressonant_backend check-structure
   make hooks                                # requires-python e namespace common
   ```
   Se o diff toca rotas ou schemas, o `test_openapi_sync` precisa passar (`openapi.json` atualizado).
3. Revise por prioridade: **Segurança > Corretude/dados > Performance > Arquitetura > Testes > Estilo**.
4. Reporte somente achados **reproduzíveis**. Se for preferência, marque como "sugestão".

## Formato do achado

```
[SEVERIDADE] arquivo:linha — problema (1 frase)
Cenário: entrada/estado → resultado errado
Correção: trecho ou instrução concreta
```

Severidades: CRÍTICA (brecha de segurança ou perda de dados), ALTA (bloqueia merge), MÉDIA (corrigir neste ciclo), BAIXA (backlog/sugestão). Termine com um veredito: aprovado, aprovado com ressalvas ou bloqueado.

## Checklist (adaptado ao código real)

**Segurança**
- Autorização por objeto: rota com `{user_id}` deve usar `AdminUser` ou `_ensure_self_or_admin`; nunca confiar em id vindo do cliente.
- Mass assignment: schemas de entrada não aceitam `interno_adm`/`status_ativo` fora do fluxo de admin (`UserRegister` vs `UserCreate`).
- Login: respostas indistinguíveis (e-mail inexistente / senha errada / conta inativa); `verify_dummy` preserva o tempo.
- Segredos: nenhum valor em código, `.env.example` com placeholder, `AUTH_SECRET` sem default.
- Dados pessoais (CPF, telefone, e-mail) fora de logs e de mensagens de erro.
- SQL parametrizado (ORM/`select`); nenhuma f-string em query.
- Para uma auditoria aprofundada, e só se o usuário pedir, use `security-best-practices`.

**Corretude e dados**
- Commit no service, `rollback` em `IntegrityError`; checagem de unicidade **mais** tratamento da violação (corrida).
- Migration revisada à mão (`upgrade` e `downgrade`), sem drift (`alembic check`); nunca editar migration já aplicada.
- Paginação com `order_by` determinístico e limites (`le=100`).

**Performance e concorrência**
- N+1: laços que consultam o banco por item; carregar com `select`/`join` explícito.
- Backend é **síncrono**: `async def` que chama `Session` síncrona, `time.sleep` ou I/O bloqueante trava o event loop. Código `async` novo sem decisão registrada é achado ALTA.
- Índices para colunas filtradas/ordenadas em volume (consulte `supabase-postgres-best-practices`).

**Arquitetura e estrutura**
- Rota fina; regra no service; acesso a dados só no repository.
- Direção de imports e limites de `check-structure`; `packages/*` nunca importa `apps/*`.
- Sem abstração prematura: wrapper que só repassa chamada, helper sem segundo uso, flag sem consumidor.
- Dependência nova só com justificativa; versões no `uv.lock` (`uv lock --check`).
- Contrato HTTP novo em snake_case (ADR 0001); **não** sinalize camelCase pré-existente.

**Tipagem e erros**
- Anotações em assinaturas públicas; `mypy` roda apenas nos hooks (`make typecheck`), então revise tipos à mão.
- Erros via `common.errors` com `error_code`; sem `HTTPException` crua, sem `except Exception` engolindo erro.

**Testes**
- Comportamento novo tem teste (sucesso, 401/403/404/409/422 quando aplicável). Teste que só cobre alias ou detalhe trivial não conta.
- Divergência conhecida: o guia `docs/guides/unit-tests.md` pede mocks e classes, mas a suíte atual usa SQLite em memória e funções. Siga o estilo do arquivo vizinho e não bloqueie por essa divergência.

**Infra (se tocada)**
- Compose, Dockerfile, CI, `.env.example` e README coerentes entre si; nenhum segredo versionado; portas em `127.0.0.1`. Use `devops-observability`.

## Não faça

- Não edite arquivos, não faça commit, não rode autofix (`make lint`) durante a revisão.
- Não apresente nitpick como bloqueio; não peça refatoração de legado fora do diff.
- Não afirme "testado" sem ter rodado o comando; cite o resultado real.
