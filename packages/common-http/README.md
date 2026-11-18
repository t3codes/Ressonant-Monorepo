# Introdução

Lib compartilhada `common.http`: política de `httpx.AsyncClient` reutilizáveis (um client por upstream, com pool de
conexões), criados no lifespan da app e fechados no shutdown. Não há wrapper de `get`/`post`: a app recebe o
`httpx.AsyncClient` e o usa diretamente.

## Por que existe

Criar um `httpx.AsyncClient` por requisição custa uma conexão TCP nova e a carga do bundle de CA a cada chamada.
Reutilizar o client resolve isso, mas expõe armadilhas que cada app teria de acertar sozinha, e errar costuma falhar só
sob carga ou em silêncio. A lib existe para que o caminho certo seja o padrão:

- **Defaults já calibrados:** timeouts e limites do pool definidos, e um `keepalive_expiry` (3 s) abaixo do idle timeout
  do uvicorn (5 s), para o client não reaproveitar uma conexão que o servidor já fechou.
- **Sem vazamento entre usuários:** o client é compartilhado, então ele descarta `Set-Cookie` em vez de guardá-lo e
  reenviá-lo a outro usuário.
- **Ciclo de vida garantido:** os clients nascem no lifespan e são fechados no shutdown, sem conexões perdidas.
- **Um ponto único de override em teste** e uma única versão do `httpx` para o monorepo, em vez de clients configurados
  de formas diferentes em cada app.

A lib não esconde o `httpx`: o que ela padroniza é a configuração do client, não o uso dele.

# Quick Start

1. Declare `common-http` nas dependências da app. Durante a transição a app mantém `httpx` direto, com o mesmo
   constraint da lib (`httpx>=0.28.1`); depois de migrar as chamadas, `httpx` sai da app e a versão fica só aqui.

2. Registre os upstreams no lifespan:

```python
from common.http import HttpClientRegistry, http_clients_lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry = HttpClientRegistry()
    registry.register("backend", base_url=settings.ressonant_backend_url)
    registry.register("auth", base_url=settings.ressonant_auth_url)  # config opcional
    async with http_clients_lifespan(app, registry):
        yield
```

3. Injete na borda (router) com `Depends` e repasse ao caso de uso pelo construtor:

```python
from common.http import http_client

BackendClient = Annotated[httpx.AsyncClient, Depends(http_client("backend"))]


@router.get("/patients/{id}")
async def get_patient(id: str, client: BackendClient, token: BearerToken):
    resp = await client.get(f"/patients/{id}", headers={"Authorization": f"Bearer {token}"})
```

Fora de request (workers, jobs), use o `HttpClientRegistry` criado no lifespan diretamente: `registry.get("backend")`.

# Configuração

A app preenche `HttpClientConfig` no lifespan e passa a `register`. Campos não informados assumem o default (ver
`common/http/config.py`).

```python
registry.register(
    "auth",
    base_url=settings.ressonant_auth_url,
    config=HttpClientConfig(read_timeout=settings.auth_read_timeout),
)
```

Sem `config`, o client usa todos os defaults.

# Erros do upstream

`translate_http_errors` e `validate_response` (`common/http/error_handler.py`) classificam as falhas de uma chamada e
deixam a app decidir qual exceção levantar. A lib não conhece o formato de erro de nenhuma app, nem o dos upstreams.

```python
def my_upstream_error(failure: UpstreamFailure) -> Exception:
    # failure.kind (FailureKind), status_code, body, text e cause: ver UpstreamFailure
    message = failure.body.get("message", "request failed")
    return MyHttpError(message=message, status_code=failure.status_code)


_ADAPTER = TypeAdapter(MyDTO)


async def get_thing(client: httpx.AsyncClient, thing_id: str) -> MyDTO:
    async with translate_http_errors("my-upstream get_thing", my_upstream_error):
        response = await client.get(f"/things/{thing_id}")
        response.raise_for_status()
        return validate_response(response, _ADAPTER.validate_json)
```

- Cada upstream tem a sua função `build_error`, porque cada um responde erro num formato diferente. Ela vive na app.
- O `status_code` de `UpstreamFailure` já vem calculado: o do upstream, 504 em timeout, 500 em falha de rede ou de pool
  e 502 em resposta inválida ou 3xx.
- `validate_response` aceita qualquer função `bytes -> objeto` que levante `ValueError` quando o corpo é inválido,
  como o `validate_json` de um `pydantic.TypeAdapter`.

# Regras

- **`keepalive_expiry` < idle timeout do servidor destino.** O uvicorn fecha conexões ociosas após 5 s (padrão), por
  isso o default é 3 s. O Keycloak usa o default do Quarkus. Os servidores não foram alterados; subir o keep-alive deles
  é uma fase futura, condicionada a medição.
- **Sem estado por usuário no client.** Credenciais vão por requisição (`headers=`). O client descarta `Set-Cookie` para
  não vazar sessão entre usuários.
- **Teste:** `app.dependency_overrides[http_client("backend")] = lambda: fake_client`.
