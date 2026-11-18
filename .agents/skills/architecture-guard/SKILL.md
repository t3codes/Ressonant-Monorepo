---
name: architecture-guard
description: Guardião arquitetural do monorepo Ressonant. Use ANTES de qualquer mudança estrutural: criar uma app em apps/, criar uma lib em packages/, mover ou renomear diretórios, mudar dependências entre módulos, mexer em check-structure, hooks, workspace uv ou ADRs, ou quando houver dúvida sobre onde um código deve ficar e quem pode importar quem.
metadata:
  scope: monorepo
  language: pt-BR
---

# architecture-guard

Consulte esta skill antes de mexer em estrutura. Ela diz **o que existe**, **o que a regra manda** e **onde as duas coisas divergem**. Não force migração: o repo declara uma migração em andamento.

## Mapa

| Caminho | Papel |
|---|---|
| `apps/ressonant_backend/` | única app hoje (FastAPI); membro do workspace uv, `package = false` |
| `packages/*` | libs sob o namespace `common` (PEP 420): `errors`, `logs`, `telemetry` (só dependências), `common-http`, `check-structure` |
| `infra/` | compose do Postgres e da observabilidade (não é código de app) |
| `docker-compose.yml` (raiz) | índice com `include:`; não define serviços |
| `hooks/` | verificações de política (pre-commit e `make hooks`) |
| `docs/` | ADRs, guias, CI/CD, compose |
| `templates/` | molde de `pyproject` de lib e `deploy-config.yaml` |

## Regras que valem hoje (fonte: hooks, check-structure, README de packages)

1. `requires-python = "==3.13.*"` em **todo** `pyproject.toml` (hook `check_requires_python_consistent.py`).
2. `packages/*/src/common/` **sem** `__init__.py` (hook `check_no_common_init.py`); a lib fica em `src/common/<lib>/__init__.py`.
3. Lib: `name = "common-<lib>"`, hatchling com `packages = ["src/common"]`, testes em `packages/<lib>/tests/`, README próprio; para ser consumida, entra em `[tool.uv.sources]` da raiz. Molde: `templates/pyproject.lib.toml`.
4. **`packages/*` nunca importa `apps/*`** (contrato `packages-no-apps`, configurado em `[tool.check-structure.platform]` na raiz). Verifique com `uv run check-structure --platform` na raiz: o `make check-structure` da raiz só percorre as apps e **não** roda essa checagem. Libs dependem de `opentelemetry-api`, nunca do SDK nem de `common-telemetry`.
5. Toda app Python depende de `common-telemetry` (nenhum `opentelemetry-*` avulso), prefixa o entrypoint de produção com `opentelemetry-instrument`, tem `OTEL_SERVICE_NAME` próprio por processo e **não** escreve código de setup de telemetria (`CLAUDE.md` histórico e `packages/telemetry/README.md`).
6. Contrato HTTP novo em snake_case (ADR 0001).
7. Código compartilhado nasce de uso real: sem API pública, shim ou kill switch sem consumidor.
8. Raiz do `check-structure` do backend: contratos de import `layers`, `common-no-modules`, `config-isolated`, `module-commons-*` (5 contratos mantidos hoje).

IDs das regras de arquivos e pastas (para `disable` e `path_exceptions`): `class-names`, `dataclasses-placement`, `dataclasses-pure`, `dto-placement`, `file-names`, `folder-names`, `module-folders`, `module-init`, `one-public-function`, `orm-models-placement`, `query-objects`, `root-folders`.

## Padrão-alvo × realidade

O guia `docs/guides/app-structure.md` descreve o **alvo** (`commons/`, `config/`, `modules/<m>/{entrypoints,usecases,services,dataproviders}`, sufixos `_router`, `_usecase`, `_service`, models com sufixo `Model`). O backend atual usa outro layout (`app/<m>/{routes,services,repository,models,schemas,deps}`), com bypasses declarados no `pyproject.toml` da app e **2 violações reportadas** pelo `make -C apps/ressonant_backend check-structure` (`User` sem sufixo `Model`; model fora de `dataproviders`). O comando não é estrito (exit 0).

- **Código novo no backend**: siga o layout existente do módulo vizinho (consistência local) e **não** misture os dois estilos no mesmo módulo.
- **Migrar para o alvo** é mudança estrutural: só com pedido explícito, em PR próprio, removendo os bypasses (`TODO`) um a um.
- Todo bypass novo exige `reason`; prefira o mais restrito (`exceptions` de um import > `path_exceptions` > `disable`).

## ADRs

- `0001` snake_case: **vigente**. Cita `ressonant-bff` e `ressonant-auth`, que **não existem** neste repo (herança de outro projeto).
- `0002` datas LME: descreve prescrições (maagizo); **não se aplica ao Ressonant**. Não use como precedente.

## Nova app (`apps/ressonant_<nome>/`)

1. Defina antes: responsabilidade, linguagem, dependência de banco/telemetria. Duas apps nunca compartilham código por import direto: se há reuso real, vira lib em `packages/` (após uso por **duas** apps ou necessidade concreta).
2. Arquivos: `Dockerfile` (contexto = raiz), `docker-compose.yml` (serviço com o nome curto `<nome>`), `.env.example`, `Makefile` com os targets padrão (`docs/guides/makefile.md`: `help`, `env`, `setup`, `up`, `test`, `lint`, `check-structure`, `ci/setup`, `ci/lint`, `ci/tests`), `README.md`, `pyproject.toml` com `package = false` e `requires-python = "==3.13.*"`.
3. Registre: include no `docker-compose.yml` da raiz (com `env_file`), whitelist `!apps/ressonant_<nome>/**` no `.dockerignore`, entrada no matrix de `.github/workflows/pr-checks.yaml` e na lista `apps` de `.cm/.gitstream.cm`.
4. `uv lock` e commit do `uv.lock` (o build Docker usa `--locked`).
5. Rode `make check` e `make check-structure`.

Detalhes operacionais: `docs/docker-compose.md`. Execute a mudança com `python-backend-specialist` e `devops-observability`; **não** crie app sem autorização explícita.

## Nova lib (`packages/<lib>/`)

Siga `packages/README.md` (molde, árvore, PEP 420, `[tool.uv.sources]`). Garanta README próprio, testes e que ela não importe nada de `apps/`. Rode `make hooks` e `make test`.

## Decisão

Antes de propor mudança estrutural, responda: (1) que regra ou ADR cobre isso? (2) o que quebra nas outras apps/libs? (3) existe a opção mais simples sem criar camada ou pacote? Se a resposta de (3) for sim, recomende-a. Registre decisões duráveis como ADR em `docs/adrs/` (modelo `0000-template.md`), **só com pedido do usuário**.
