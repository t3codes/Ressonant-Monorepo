# CI/CD

Documentação dos workflows de integração contínua e testes do monorepo.

---

## Estado atual

Esta fase **removeu** os workflows de deploy (`deploy-devqa.yaml`, `deploy-staging.yaml`,
`deploy-production.yaml` e o reusable `build-image-to-ecr-v2.yaml`), incluindo o fluxo
CI/CD. Mantém-se apenas o que é de CI/CD imediato:

| Workflow | Papel |
| --- | --- |
| `pr-checks.yaml` | Roda no PR; dispara `test-and-lint-app.yaml` no matrix de apps. |
| `test-and-lint-app.yaml` | Reusable: `make ci/setup`, `make ci/lint`, `make ci/tests` no `apps/<app_name>`. |
| `integration-test-app.yaml` | Reusable: roda suíte de integração contra ambiente deployado. |
| `integration-test-devqa.yaml` | Wrapper DEV/QA da integration suite. |
| `integration-test-staging.yaml` | Wrapper Staging da integration suite. |
| `gitstream.yml` | Automações de PR (labels/review). |

O deploy ficou fora do escopo desta fase; o conteúdo anterior do documento
foi removido junto com os workflows.

---

## Workflow: Test and Lint (`test-and-lint-app.yaml`)

Reutilizado como step nos PRs via `pr-checks.yaml`.

### Funcionamento

O workflow recebe o input `app_name`, faz checkout do repositório e executa três comandos Make no diretório `apps/<app_name>`:

1. **`make ci/setup`** — Instala as dependências e prepara o runner do GitHub Actions para o lint e os testes.
2. **`make ci/lint`** — Executa as verificações de lint/formatação. Deve retornar exit code diferente de zero caso encontre problemas, fazendo o workflow falhar.
3. **`make ci/tests`** — Executa a suíte de testes do projeto.

Toda app em `apps/<app_name>` fornece um `Makefile` com esses targets, seguindo [o guia de Makefile](guides/makefile.md#3-targets-de-ci).

---

## Workflow: Integration Test (`integration-test-app.yaml`)

Executa a suíte de testes integrados de uma app contra a versão já deployada. Reusable, acionado manualmente por dois wrappers:

| Workflow | Inputs | Environment | Runner |
| --- | --- | --- | --- |
| `integration-test-devqa.yaml` | `app_name`, `stack-name` | `development` | `dev-runner` |
| `integration-test-staging.yaml` | `app_name` | `staging` | `ubuntu-latest` |

O job exporta as variáveis declaradas em `integration_tests.<environment>` do `deploy-config.yaml` da app, trocando `__STACK_NAME__` pelo input `stack-name` (ver [Configuração por app](#configuração-por-app-deploy-configyaml)). Depois roda, em `apps/<app_name>`, dois steps: `make ci/integration-test`, que executa a suíte só com as dependências dela, sem instalar a app; e, apenas se a suíte passar, `make ci/integration-test/inventory`, que gera o inventário de cobertura com a app completa (ele importa a app para ler as rotas). O resultado e o inventário vão para o Step Summary.

Para habilitar uma app: crie `integration_tests/` (ver [`docs/guides/integration-tests.md`](guides/integration-tests.md)), os targets `ci/integration-test` e `ci/integration-test/inventory` no `Makefile`, o bloco `integration_tests` no `deploy-config.yaml` da app e adicione a app nas `options` dos dois wrappers.

---

## Referências

- [integration-tests.md](guides/integration-tests.md) — guia completo de testes integrados.
- [docker-compose.md](docker-compose.md) — orquestração local com Docker Compose.
