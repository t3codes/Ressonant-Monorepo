# Revisão Estrutural do Monorepo — Backend Ressonant

**Data:** 2026-11-18  
**Escopo:** `ressonant-monorepo-work/` (fora para dentro)  
**Status:** Seguro para limpeza (com ressalvas)

---

## 1. Resumo executivo

O monorepo tem uma base sólida: workspace `uv` com `apps/*` e `packages/*`, docker-compose modular via `include:`, Docker multi-stage bem construído, testes em SQLite sem Docker, OpenAPI versionado, collections Postman/Insomnia separadas, e `AGENTS.md` como fonte única de verdade. Segredos não estão versionados.

Após a reestruturação recente de `app/` em `modules/<dominio>/{entrypoints,usecases,dataproviders,schemas,domain}`, há inconsistências de configuração e alguns artefatos de build que estão sendo versionados indevidamente.

---

## 2. O que está bem (funcionando, consistente)

| Item | Status | Evidência |
|------|--------|-----------|
| Workspace `uv` com `apps/*` + `packages/*` | ✅ | `pyproject.toml:28` |
| Docker multi-stage (manifests → builder → runtime) | ✅ | `apps/ressonant_backend/Dockerfile` |
| docker-compose com `include:` modular | ✅ | `docker-compose.yml` (raiz) |
| Testes em SQLite sem Docker | ✅ | `tests/conftest.py`, `make test` |
| OpenAPI versionado + teste de sincronia | ✅ | `openapi.json`, `test_openapi_sync.py` |
| Collections Postman/Insomnia separadas (não executáveis) | ✅ | `apps/ressonant_collections/` |
| `AGENTS.md` como fonte única de verdade | ✅ | Raiz do monorepo |
| Secrets não versionados (`.env` no `.gitignore`) | ✅ | `.gitignore:36` |
| Estrutura modular `app/modules/` implementada | ✅ | 3 domínios (auth, user, workspace) |
| `app/common/` preservado (recomendação do Stark) | ✅ | Intocado |

---

## 3. O que precisa mudar (inconsistências e configurações defasadas)

### 3.1 Configuração `check-structure` desatualizada (MÉDIO)

O `pyproject.toml` do backend ainda aponta para o layout antigo:

```toml
[tool.check-structure]
root_package = "app"
modules_package = "app"          # TODO: migrar para o padrão modules/
common_package = "app.common"
module_commons = "common"
disable = ["root-folders"]
```

Após a criação de `app/modules/`, essas chaves precisam ser atualizadas para refletir o novo layout. Caso contrário, `make check-structure` pode falhar ou validar a estrutura errada.

**Arquivo:** `apps/ressonant_backend/pyproject.toml:44-53`

### 3.2 README do backend aponta para coleção fora do monorepo (BAIXO)

```markdown
Collection Postman em `../ressonant-api-collections` (fora do monorepo).
```

Agora a coleção está dentro do monorepo em `apps/ressonant_collections/`.

**Arquivo:** `apps/ressonant_backend/README.md:3`

### 3.3 `uv.lock` pode estar desatualizado (BAIXO)

Após mudanças nas dependências (nova estrutura interna não muda deps, mas worth verificar se `uv lock` bate com os `pyproject.toml` atuais).

**Arquivo:** `uv.lock`

### 3.4 `agent/` diretório na raiz (BAIXO)

Existe um diretório `agent/` na raiz que não está documentado no `AGENTS.md` nem no `README.md`. Não está claro se é usado ou é artefato antigo.

**Caminho:** `/home/tharlleste/Documentos/Projetos_Pessoais/workspace/ressonant-monorepo-work/agent/`

---

## 4. Arquivos inúteis / sujeira para limpar

### 4.1 Build artifacts versionados (CRÍTICO para limpeza)

O diretório `ressonant_backend.egg-info/` está sendo versionado no git. Isso é um artifact de build e não deveria estar no repositório.

**Caminho:** `apps/ressonant_backend/ressonant_backend.egg-info/`

Verificação: `git check-ignore` confirma que o `.gitignore` tem `*.egg-info/` mas o diretório foi adicionado antes ou está sendo rastreado.

### 4.2 Caches locais versionados (MÉDIO)

Diretórios de cache podem estar versionados:
- `apps/ressonant_backend/.pytest_cache/`
- `apps/ressonant_backend/.ruff_cache/`
- `apps/ressonant_backend/app/__pycache__/`
- `.pytest_cache/` (raiz)
- `.ruff_cache/` (raiz)
- `.mypy_cache/` (raiz)

### 4.3 `.artifacts/` (BAIXO)

O diretório `.artifacts/` foi criado para guardar relatórios de auditoria e pareceres. É um diretório de trabalho, não deveria ser versionado. Pode ser movido para `.gitignore` ou mantido fora do commit.

**Caminho:** `.artifacts/`

---

## 5. Recomendações de estrutura de monorepo

1. **Atualizar `check-structure`** no `pyproject.toml` do backend para refletir `app/modules/`
2. **Atualizar README** do backend para apontar para `apps/ressonant_collections/`
3. **Adicionar `ressonant_collections` ao docker-compose** raiz (opcional — como não é serviço, pode ficar fora, mas documentar)
4. **Remover `egg-info/` do versionamento** via `git rm --cached`
5. **Adicionar caches ao `.gitignore`** se não estiverem lá (verificar)
6. **Rodar `uv lock`** para sincronizar o lockfile
7. **Documentar `agent/`** ou remover se não for usado

---

## 6. Seguro para fazer limpeza?

**SIM**, com as seguintes guardrails:

- ✅ **Não remover código funcional**: apenas arquivos de build artifact (egg-info, caches)
- ✅ **Não alterar rotas nem schemas**: a limpeza é de estrutura/configuração apenas
- ✅ **Executar `make test` e `make lint`** após cada mudança para garantir que nada quebrou
- ✅ **Commitar apenas arquivos nomeados**, nunca `git add -A`
- ✅ **Não fazer push** (regras do PROMPT_EXPANSAO_BACKEND)

---

## 7. Top 3 achados

1. **`egg-info/` versionado** — artifact de build no git, deve ser removido do versionamento
2. **`check-structure` desatualizado** — `pyproject.toml` ainda aponta para layout antigo (`modules_package = "app"`) após a criação de `app/modules/`
3. **README desatualizado** — aponta para coleção fora do monorepo quando ela agora está dentro

**Recomenda prosseguir com limpeza?** SIM — começar pelo `egg-info/` e `check-structure`, que são de baixo risco e alto impacto.
