# Introdução

Lib compartilhada de exceções padronizadas para o ecossistema Ressonant. Fornece uma hierarquia de erros HTTP (`BadRequestException`, `NotFoundException`, `UnexpectedException`, etc.) com conversão automática para schema de resposta, garantindo um formato de erro consistente entre todos os serviços do monorepo.

# Quick Start

1. Adicione `common-errors` como dependência do seu pacote:

```bash
uv add --package <seu-pacote> common-errors
```

2. Lance exceções nos seus serviços:

```python
from common.errors.exception_data import ExceptionData
from common.errors.exceptions import NotFoundException

raise NotFoundException(
    ExceptionData(
        message="Prescrição não encontrada",
        detail="Nenhuma prescrição com o ID fornecido",
    )
)
```

Quando `error_code` não é informado, a exceção assume o nome HTTP padrão do status (e.g. `NOT_FOUND`, `BAD_REQUEST`).

3. Para usar um código de erro customizado:

```python
from common.errors.exception_data import ExceptionData
from common.errors.exceptions import BadRequestException

raise BadRequestException(
    ExceptionData(
        message="CPF inválido",
        detail="O CPF informado não passou na validação",
        error_code="INVALID_CPF",
    )
)
```

4. Para adicionar uma dependência externa à lib:

```bash
uv add --package common-errors <dependencia>
```

5. Para rodar os testes:

```bash
uv run pytest packages/errors
```

# Deploy

Biblioteca interna do monorepo — não possui deploy independente. É distribuída como workspace member do UV e consumida diretamente pelos pacotes e aplicações do monorepo.

# Códigos de erro

`CommonErrorCode` contém apenas códigos de erro **comuns e genéricos**, reutilizáveis por qualquer aplicação do monorepo (ex.: `UNEXPECTED_ERROR`, `HTTP_INTEGRATION_ERROR`).

Códigos de erro **específicos de domínio** devem ser definidos dentro de cada aplicação, em `/apps`, usando um `StrEnum` próprio do app.

# Exception Handlers

A função `setup_exception_handlers` registra handlers globais de exceções em uma aplicação FastAPI, garantindo que toda resposta de erro siga o formato padronizado (`ErrorSchema`) e, opcionalmente, inclua um **trace reference ID** do OpenTelemetry para rastreabilidade.

## Uso

Chame `setup_exception_handlers` passando a instância da aplicação FastAPI durante a inicialização:

```python
from fastapi import FastAPI
from common.errors.exception_handlers import setup_exception_handlers

app = FastAPI()
setup_exception_handlers(app)
```

## Handlers registrados

Os handlers disponibilizados pela biblioteca podem ser visualizados no arquivo [`exception_handlers.py`](src/common/errors/exception_handlers.py).

## Formato de resposta

Todos os handlers retornam um `JSONResponse` com o corpo no formato `ErrorSchema`:

```json
{
  "status_code": 404,
  "message": "Prescrição não encontrada",
  "detail": "Nenhuma prescrição com o ID fornecido",
  "error_code": "NOT_FOUND",
  "error_messages": null
}
```

Para exceções da aplicação (`ApplicationException` e subclasses), o campo `detail` contém o valor informado pelo desenvolvedor no `ExceptionData`. Para handlers genéricos (erros não tratados, validação de payload e exceções HTTP do Starlette), o campo `detail` contém o **trace reference ID** extraído do span corrente do OpenTelemetry, facilitando a correlação com logs e traces em ferramentas de observabilidade.

## Formato de resposta customizado

Aplicações cujo contrato de erro difere do `ErrorSchema` passam um renderer para `setup_exception_handlers`. Herde de `DefaultErrorRenderer` e sobrescreva apenas os métodos cujo formato muda — os demais mantêm o comportamento padrão.

```python
from common.errors import DefaultErrorRenderer, setup_exception_handlers

class MeuErrorRenderer(DefaultErrorRenderer):
    def render(self, exc):
        data = exc.exception_data
        return exc.status_code, {"message": data.message, "code": data.error_code}

    def render_http(self, exc):
        return exc.status_code, {"message": str(exc.detail)}

setup_exception_handlers(app, MeuErrorRenderer())
```

Cada método devolve a tupla `(status_code, body)`. O `body` é serializado com `jsonable_encoder`, então pode ser um `dict` ou um modelo Pydantic. Log, nível de log e transporte da resposta continuam a cargo dos handlers — o renderer decide apenas o conteúdo.

Os métodos disponíveis e a situação em que cada um é chamado estão em [`renderers/protocol.py`](src/common/errors/renderers/protocol.py).

# Exceções disponíveis

As exceções disponibilizadas pela biblioteca podem ser visualizadas no arquivo [`exceptions.py`](src/common/errors/exceptions.py).

Todas herdam de `ApplicationException`, que expõe `exception_data` (os dados do erro) e `to_dict()`. Montar o corpo da resposta a partir desses dados é responsabilidade do renderer, não da exceção — ver seção anterior.

## Exceções especializadas

Quando o mesmo erro se repete em um domínio, crie uma exceção própria herdando da exceção HTTP correspondente. Ela encapsula a montagem do `ExceptionData` e o código de erro, e o ponto de lançamento fica com uma linha só.

```python
from common.errors import ExceptionData, NotFoundException

class PhysicianNotFoundException(NotFoundException):
    def __init__(self, physician_id: str):
        super().__init__(
            ExceptionData(
                message="Médico não encontrado",
                detail=f"physician_id={physician_id}",
                error_code=PhysicianErrorCode.PHYSICIAN_NOT_FOUND,
            )
        )

raise PhysicianNotFoundException(physician_id)
```

O status HTTP vem da classe herdada (`NotFoundException` → 404), então a subclasse cuida apenas do conteúdo do erro.

## Erros esperados (`is_expected`)

Toda `ApplicationException` aceita `is_expected: bool = False`. Quando `True`, `application_exception_handler` não loga a exceção como `ERROR` — o erro ainda vira a resposta HTTP normalmente, só não polui o log como se fosse uma falha a investigar.

```python
raise NotFoundException(
    ExceptionData(message="Prescrição não encontrada"),
    is_expected=True,
)
```

O status HTTP (nem 4xx) não decide isso sozinho: é o código que levanta a exceção quem sabe se aquele erro é um resultado normal do fluxo de negócio ou uma falha real — por isso o default é `False`.

