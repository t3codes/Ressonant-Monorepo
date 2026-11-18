# Testes unitários

Guia dos testes unitários de todas as apps do monorepo: por que eles são escritos assim, as regras que seguem e como
executá-los. Ao final, você saberá criar um teste unitário que roda em milissegundos, falha só quando o código muda e
não depende de nada fora do processo.

## Introdução

O teste unitário prova que a lógica da app está certa: regras, mapeamentos e tratamento de erro. Ele roda na máquina de
quem desenvolve e em toda PR, e por isso precisa ser rápido, repetível e isolado. A comparação com o teste integrado,
que prova a app conectada ao ambiente, está na [introdução de `integration-tests.md`](integration-tests.md#introdução).

### Por que tudo é mockado

Um teste que fala com um banco, uma API ou uma fila de verdade passa a depender de rede, de credencial e do estado de
outro sistema. Ele fica lento, falha sem que o código tenha mudado e, quando falha, não aponta a causa. Provar a
integração é papel do teste integrado; o unitário troca a dependência por um mock e controla exatamente o que ela
devolve, o que permite provocar qualquer cenário, inclusive os que o ambiente real não reproduz (timeout, 503,
payload quebrado).

### Por que nenhuma espera é real

Um retry com backoff exponencial de 1, 2 e 4 segundos adiciona 7 segundos a cada cenário de falha. Multiplicado pelos
cenários da suíte, isso vira minutos em toda PR, sem provar nada a mais: o que importa é quantas vezes o código tentou
e o que fez depois, não quanto tempo esperou.

### Por que classes

A classe externa agrupa os cenários de um alvo e as aninhadas separam sucesso de erro. Na saída do `pytest -v`, os
testes se leem como uma especificação (`TestFindPharmacy::TestErrors::test_should_raise_...`), e o mesmo caminho
seleciona um alvo inteiro ou só um tipo de cenário na execução.

## 1. Princípios

- Tudo que sai do processo é mockado: banco, HTTP, filas, Redis, storage e autenticação. Um teste que
  deixa uma integração real acontecer é integrado e segue [`integration-tests.md`](integration-tests.md).
- O teste de uma camada mocka as dependências que ela chama diretamente (services, dataproviders), nunca as de mais
  abaixo; assim, o resultado de cada dependência é controlado e todos os cenários da camada são provocados. DTOs e
  funções puras não são mockados.
- Nenhuma espera é real: `sleep`, backoff de retry e timeout são substituídos no teste.
- Cada teste é independente: não depende da ordem de execução nem de estado deixado por outro teste.
- A configuração vem de `Settings` construído no teste (fixture `make_settings`), nunca do `.env` ou de variável de
  ambiente real.

## 2. Estrutura

- `tests/` espelha o pacote da app: o teste fica no mesmo caminho do arquivo testado, com o prefixo `test_`.

  ```
  app/pharmacy/dataproviders/rest/find_pharmacy.py
  tests/pharmacy/dataproviders/rest/test_find_pharmacy.py
  ```

- Um arquivo de teste por arquivo de código. Todo diretório de `tests/` tem `__init__.py`.
- Fixtures usadas por vários arquivos ficam no `conftest.py` mais próximo de todos eles; fixture de um arquivo só fica
  no próprio arquivo.
- Valor repetido no arquivo (URL, id, token, payload) vira constante em maiúsculas no topo do arquivo, como
  `PHARMACY_URL` no [exemplo](#exemplo). O teste passa a dizer o que o valor representa, e uma mudança nele é feita
  num só lugar.

## 3. Classes e nomes

```python
@pytest.mark.asyncio
class TestFindPharmacy:
    class TestSuccess:
        async def test_should_return_pharmacy_when_it_exists(self) -> None: ...

    class TestErrors:
        async def test_should_raise_pharmacy_not_found_error_when_service_returns_404(self) -> None: ...
```

- Cada função ou classe pública testada tem uma classe externa `Test<Alvo>`, com o nome do alvo em PascalCase
  (`find_pharmacy` → `TestFindPharmacy`).
- Dentro dela há uma classe aninhada por tipo de cenário, criada só quando o tipo tem cenário: `TestSuccess` (caminho
  feliz e variações) e `TestErrors` (falhas e como o código as trata).
- Os nomes seguem `test_should_<resultado_esperado>_when_<condição>`; quando o resultado é uma exceção,
  `test_should_raise_<erro>_when_<condição>`. O `_when_<condição>` só é omitido quando não há condição a distinguir.
- Um cenário por método. Casos com a mesma ação e a mesma asserção, que mudam só o dado de entrada (status, exceção
  injetada, corpo), são variações do mesmo cenário e usam `pytest.mark.parametrize`.
- Testes `async` levam `@pytest.mark.asyncio` na classe externa, que vale para as aninhadas (`asyncio_mode = "strict"`).
- Fixtures `async` levam `@pytest_asyncio.fixture`: no modo `strict`, `@pytest.fixture` não as executa.

## 4. Entrypoints

Routers REST:

- O router é chamado em processo (`TestClient`), com o usecase e as dependências (autenticação) trocados
  por `dependency_overrides`. Nenhum servidor sobe e nenhuma chamada sai do processo.
- O teste verifica:
  - as validações que o time escreveu no schema: validators próprios, limites, campos obrigatórios e nomes das chaves do
    contrato. Validação que é só do Pydantic (tipo do campo) não é testada;
  - o despacho para o usecase: ele é chamado uma vez, com o DTO montado a partir da entrada;
  - a resposta: status e corpo convertidos a partir do retorno do usecase, inclusive nos erros que ele lança.

## 5. Dataproviders

Clients HTTP:

- O transporte é mockado com `respx`, ativado por uma fixture `autouse` com `with respx.mock:`; o client real monta a
  requisição e lê a resposta. Requisição sem rota declarada faz o teste falhar.
- O `@respx.mock` não decora a classe de testes: o `respx` a troca por uma função e o `pytest` deixa de coletar os
  testes.
- O teste verifica:
    - a requisição enviada: método, URL, query string, headers e corpo;
    - a tradução da resposta para o DTO, inclusive com campos opcionais ausentes;
    - a tradução de cada falha (status não esperado, timeout, erro de conexão, payload fora do contrato) para a exceção
      de domínio da app: nenhum erro do `httpx` ou do Pydantic escapa do client;
    - quando há retry, o número de tentativas e quais falhas são (ou não) tentadas de novo.
- A espera entre tentativas é trocada por zero (com `tenacity`, `tenacity.wait_none()`). O teste verifica o número de
  chamadas, nunca o tempo decorrido.

## Exemplo

Client fictício `app/pharmacy/dataproviders/rest/find_pharmacy.py`, com uma operação por arquivo: a função
`find_pharmacy` busca uma farmácia num serviço externo, repete a chamada até 3 vezes quando ele está indisponível
(`tenacity`, com a espera em `_WAIT`) e traduz as falhas para `PharmacyNotFoundError` e `PharmacyUnavailableError`.

O teste fica em `tests/pharmacy/dataproviders/rest/test_find_pharmacy.py`:

```python
PHARMACY_ID = "123"
PHARMACY_URL = f"https://pharmacy.test/v1/pharmacies/{PHARMACY_ID}"


@pytest.fixture(autouse=True)
def _mock_transport() -> Iterator[None]:
    with respx.mock:
        yield


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.pharmacy.dataproviders.rest.find_pharmacy._WAIT", tenacity.wait_none())


@pytest.mark.asyncio
class TestFindPharmacy:
    class TestSuccess:
        async def test_should_return_pharmacy_when_it_exists(self) -> None:
            route = respx.get(PHARMACY_URL).respond(200, json={"name": "Farmácia Central"})

            result = await find_pharmacy(PHARMACY_ID)

            assert route.calls.last.request.headers["accept"] == "application/json"
            assert result.name == "Farmácia Central"

    class TestErrors:
        async def test_should_raise_pharmacy_not_found_error_when_service_returns_404(self) -> None:
            respx.get("https://pharmacy.test/v1/pharmacies/999").respond(404)

            with pytest.raises(PharmacyNotFoundError):
                await find_pharmacy("999")

        async def test_should_raise_pharmacy_unavailable_error_when_service_keeps_returning_503(self) -> None:
            route = respx.get(PHARMACY_URL).respond(503)

            with pytest.raises(PharmacyUnavailableError):
                await find_pharmacy(PHARMACY_ID)

            assert route.call_count == 3
```

- A fixture `_mock_transport` ativa o `respx` em todos os testes do arquivo. Ele intercepta o `httpx` antes da rede: o
  client executa o código real de montar a requisição e ler a resposta, e nenhuma chamada sai do processo.
- O caminho feliz verifica as duas pontas da tradução: o que foi enviado (o header) e o DTO devolvido.
- O cenário de 503 roda instantâneo graças à fixture `_no_backoff`, e prova o retry pela contagem de chamadas.

## Como executar

A partir de `apps/<app>`:

```sh
make test                                                   # suíte completa
uv run pytest tests/pharmacy/dataproviders/rest/test_find_pharmacy.py
uv run pytest tests/pharmacy/dataproviders/rest/test_find_pharmacy.py::TestFindPharmacy::TestErrors
uv run pytest tests -k find_pharmacy                        # por trecho do nome
```
