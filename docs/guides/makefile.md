# Makefile das apps

Este guia descreve a convenção do `Makefile` de cada app em `apps/<app>/`. Ao final, você sabe quais targets uma app
expõe, como nomeá-los e onde o CI e o Docker entram.

## Introdução

O `Makefile` é a interface única da app: o dev, o CI e quem entra no time rodam os mesmos comandos, sem precisar saber
se a app usa `uv`, Docker ou outra ferramenta. Quando cada app inventa seus próprios nomes e variações, o comando que
funciona em uma falha em outra, e o CI passa a testar algo diferente do que o dev roda localmente.

O CI de lint e testes (`test-and-lint-app.yaml`) é o mesmo para todas as apps e só chama `make ci/setup`,
`make ci/lint` e `make ci/tests`. Por isso `ci/setup` e `ci/tests` chamam `setup` e `test`, e `ci/lint` roda as
mesmas verificações de `lint` sem escrever arquivos: o que passa no CI é o que passa na máquina do dev.

## 1. Targets padrão

- **`help`** é o target `default` e lista os targets a partir do comentário `# descrição` na mesma linha.
- **`env`** cria o `.env` a partir do `.env.example` quando ele não existe.
- **`setup`** depende de `env` e instala só as dependências da app com `uv sync --locked`, para que um lockfile
  desatualizado falhe em vez de ser resolvido de novo em silêncio. Instalar o workspace inteiro é papel do
  `make setup` da raiz.
- App sem `dependency-groups` próprio, que usa o `pytest` e o `ruff` do grupo `dev` da raiz, instala com
  `uv sync --locked --all-groups --package <app>`; sem `--all-groups`, essas ferramentas não são instaladas.
- **`up`** sobe a app localmente, sem Docker, com reload.
- **`test`** roda a suíte de testes.
- **`lint`** roda o linter e o formatter com autofix (escreve arquivos).
- **`check-structure`** roda a verificação de estrutura (`STRICT=1` falha em violação).
- Targets específicos da app (`migrate/*`, `storage/*`, `integration-test`) existem só quando a app precisa deles.
- App com migrations expõe `migrate/generate msg="<descrição>"`, que falha sem `msg`, e `migrate/apply`.

## 2. Targets de Docker

- Target que gerencia o ambiente Docker Compose da app, ou que roda no container um target local, tem o prefixo
  `docker/` e um alias curto com `d` na frente: `docker/up dup`, `docker/watch dwatch`, `docker/down ddown`,
  `docker/clean dclean`, `docker/logs dlogs`, `docker/build dbuild`, `docker/test dtest`, `docker/migrate dmigrate`.
  A app expõe só os que usa; quando expõe, usa esse nome e esse alias.
- Exceção: tarefa específica da app que só executa um comando dentro de um container já rodando (ex.: `storage/*`,
  `export`) leva o nome da tarefa, sem o prefixo, porque não tem equivalente local.
- O Compose é chamado pela variável `COMPOSE := docker compose -f $(APP_DIR)/<arquivo>`, para o target funcionar
  também quando chamado de fora do diretório da app (`make -C apps/<app>`).
- Profiles opcionais entram com `$(if $(PROFILES),--profile $(PROFILES),)`; `--profile` com valor vazio quebra o
  comando.

## 3. Targets de CI

- **`ci/setup`** prepara o runner do GitHub Actions para o lint e os testes.
- **`ci/lint`** é a versão sem escrita de `lint`: só verifica e falha se encontrar problema.
- **`ci/tests`** roda a suíte de testes.
- Os targets `ci/*` rodam com `uv` direto no runner, sem Docker: `ci/setup` garante o `uv` e chama `make setup`, e
  `ci/tests` chama `make test`, para que o CI rode o mesmo comando que o dev.
- Exceção: uma app cujo lint ou teste precise de dependência de sistema que o runner não tem roda `ci/*` no Compose e
  explica o motivo em um comentário no próprio target.
- Apps sem código Python (ex.: realm do Keycloak) mantêm os três targets `ci/*` com a ferramenta que fizer sentido.

## 4. Organização do arquivo

- O arquivo começa com `default: help`, seguido das variáveis (`APP_DIR`, `COMPOSE`, `PROFILES`) e de um único
  `.PHONY` com todos os targets, aliases incluídos.
- Todo target feito para o dev chamar tem o comentário `# descrição` na linha da regra; sem ele, o target não aparece
  no `help`.

## Exemplo

Trecho do `Makefile` de uma app fictícia `pharmacy-api`:

```make
default: help

APP_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
COMPOSE := docker compose -f $(APP_DIR)/docker-compose.yml

ENSURE_UV := command -v uv >/dev/null 2>&1 || { curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh && sh /tmp/uv-install.sh; }

export PATH := $(HOME)/.local/bin:$(PATH)

.PHONY: help env setup up test lint docker/up dup docker/test dtest ci/setup ci/lint ci/tests

setup: env # Install locked dependencies for the app.
	uv sync --locked

test: # Run app tests.
	uv run pytest tests

docker/test dtest: # Run the app tests using docker.
	$(COMPOSE) run --rm --no-deps pharmacy-api uv run pytest tests

ci/setup: # CI: ensure uv is available and install dependencies (called by test-and-lint-app.yaml).
	$(ENSURE_UV)
	$(MAKE) setup

ci/lint: # CI: run linter and format check without writing files.
	uv run ruff check .
	uv run ruff format --check .

ci/tests: # CI: run the test suite.
	$(MAKE) test
```

`ENSURE_UV` instala o `uv` só no runner, onde ele não vem instalado; na máquina do dev o `command -v` encerra a linha.
O `export PATH` deixa o `uv` recém-instalado visível para os targets seguintes. `ci/tests` não repete o comando do
pytest: muda o `test`, muda o CI junto.

## Como executar

Rode `make` dentro de `apps/<app>/` para listar os targets. Para reproduzir o CI localmente:

```bash
make ci/setup ci/lint ci/tests
```
