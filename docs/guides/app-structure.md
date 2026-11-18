# Estrutura das apps

Este documento instrui sobre as padronizações estabelecidas para as apps do monorepo, explicando um pouco de suas
motivações e as regras em si: como organizar pastas, arquivos, nomes e imports. Ao final, você saberá onde cada código
deve ficar, o que cada camada significa, as convenções de nomenclatura e regras de acoplamento.

## Por que padronizar

Para tornar o entendimento das aplicações do monorepo mais simples e rápido, priorizamos a padronização — desde as tasks
do Makefile, estrutura dos projetos e convenções de nomenclatura, até as versões de bibliotecas e dependências. Dessa
forma, ao entender uma aplicação, entende-se todas.

Por isso, definimos uma estrutura que, se seguida à risca, traz essas vantagens, além de abrir espaço para reutilizações
e abstrações entre as apps e otimizar o contexto para modelos de IA.

Seguir a padronização também evita problemas comuns e recorrentes, como o acoplamento entre implementações, que faz uma
mudança simples gerar efeitos colaterais em outros pontos, e mitiga bugs decorrentes disso.

A maioria das regras são verificadas automaticamente pela lib
[`check-structure`](../../packages/check-structure/README.md) (`make check-structure`), que aponta cada violação.

> **Migração em andamento.** As apps estão sendo migradas para este formato. Por um período, código que viola estas
> regras (pastas no singular, ausência de `modules/`, arquivos sem o sufixo esperado) coexiste com o formato ideal. O
`check-structure` reporta essas violações sem bloquear: cada app declara em seu `pyproject.toml` o que ainda difere do
> padrão (ver [Criando um bypass](#5-criando-um-bypass)). Código novo deve seguir este guia.

## 1. Estrutura alvo

```
<app>/
├── commons/                # código compartilhado entre módulos
├── config/                 # settings e configuração
└── modules/
    └── <modulo>/           # um módulo de negócio
        ├── entrypoints/    # rest/, messaging/ (rotas e consumers)
        ├── usecases/       # orquestra um caso de uso
        ├── services/       # regras de negócio (opcional)
        ├── dataproviders/  # I/O: banco, HTTP, filas
        └── commons/        # código compartilhado só dentro do módulo
```

- Um módulo só tem as quatro camadas acima e `commons/`. Qualquer outra pasta é violação.
- Todo módulo e toda camada têm `__init__.py`. Sem ele, a pasta fica fora de todas as checagens de import.
- Além de `commons/`, `config/` e `modules/`, a raiz só aceita `docs/` e `infrastructure/`.
- `dataclasses/` (DTOs e QueryObjects) e `schemas/` são pastas que podem existir dentro de qualquer camada.
- Models ORM ficam em `dataproviders/repository/models/`.

### Layers no detalhe

Uma requisição entra pelo `entrypoint`, que chama um `usecase`; o `usecase` conduz o fluxo usando `services` e
`dataproviders`. Cada camada tem um papel, e o que não é dela é delegado.

- **`entrypoints`: porta de entrada.** Recebe HTTP (`rest/`, com routers e `schemas/`) ou mensagens (`messaging/`),
  converte a entrada em DTO, chama um usecase e converte a resposta. Não tem regra de negócio nem acessa banco ou
  serviços externos.
- **`usecases`: orquestra um caso de uso.** Um arquivo por caso de uso, com uma função pública que se lê como uma
  receita ("busca, valida, salva, notifica"), chamando `services` e `dataproviders`. Não conhece detalhes de HTTP, SQL
  ou payload externo. Funciona como camada anti-corrupção: o mesmo usecase pode atender mais de um entrypoint (uma rota
  REST e um consumer, por exemplo), e por isso recebe e devolve seus próprios DTOs (em `usecases/dataclasses/`), nunca o
  schema de um entrypoint. Assim, mudar o contrato de uma rota não quebra o consumer, e vice-versa: cada entrypoint
  converte seu formato para o DTO do usecase.
- **`services`: regras de negócio e código reaproveitado.** Opcional: só existe quando há regra de negócio ou lógica que
  se repetiria em vários usecases. Ex.: buscar um médico e lançar erro se ele não existir, usado por vários usecases,
  vira um service; uma chamada única sem lógica ao redor é feita pelo usecase direto no `dataprovider`, sem um service
  que apenas a repasse. No bff, preferencialmente não há regra de negócio (é papel dos backends), e `services` se limita
  a compor e transformar dados.
- **`dataproviders`: fronteira com o mundo externo.** Acessa banco (`repository/`), APIs e filas, e é a única camada que
  conhece URL, payload e esquema de tabela; traduz o formato externo para o interno, para que mudanças lá fora fiquem
  restritas aqui. Sua única responsabilidade é a integração: não tem regra de negócio nem adapta dados para a tela ou
  para o contrato de resposta de uma rota (mensagens, títulos, formatos de exibição). Essa adaptação é feita em outro
  ponto (o handler de exceção, no caso de erros); o `dataprovider` só entrega o dado traduzido.
  - **Resposta de API:** o client valida e converte o corpo direto para o DTO, com um `pydantic.TypeAdapter` criado
    uma vez no nível do módulo (`validate_json(response.content)`) em vez de a cada chamada. Corpo fora do contrato
    vira exceção de domínio, nunca um `ValidationError` solto.

`commons/` guarda o que é usado por várias camadas: dependências do FastAPI (`Depends`, ex.: autenticação e feature
flags), erros e utilitários (paginação, Redis). Erros vêm quase prontos da lib [
`common-errors`](../../packages/errors/README.md), com exceções HTTP, formato de resposta e handlers (
`setup_exception_handlers(app)` na inicialização); a app só define seus códigos de erro de domínio em
`commons/errors/` (ou no `commons/` do módulo, se forem só dele).

## 2. Direção dos imports

Uma camada importa a si mesma ou as que estão abaixo dela, em qualquer módulo:

```
entrypoints → usecases → services → dataproviders
```

Por exemplo, `usecases` pode importar `services`, mas `services` nunca importa `usecases` nem `entrypoints`.

| Pasta                  | Pode importar                                                                            | Não pode importar                                           |
|------------------------|------------------------------------------------------------------------------------------|-------------------------------------------------------------|
| `commons/` (raiz)      | `commons`, `config`                                                                      | `modules`                                                   |
| `config/`              | `config`                                                                                 | `modules`, `commons`                                        |
| `dataclasses/`         | `commons` (raiz e do módulo) e `dataclasses/` do mesmo módulo, na mesma camada ou abaixo | qualquer outra coisa, inclusive a própria camada e `config` |
| `modules/<m>/commons/` | `commons` (raiz), `config`, ele mesmo                                                    | camadas do módulo, outros módulos                           |

`commons/` existe em dois níveis: na raiz, compartilhado por todos os módulos, e dentro de um módulo, compartilhado só
entre as camadas dele. Os `commons/` de um módulo não são importados por outros módulos. Bibliotecas externas (FastAPI,
SQLAlchemy etc.) não entram nessas regras.

As shared libs do monorepo (`packages/*`) são usadas pelas apps, mas nunca o contrário: nenhuma shared lib pode importar
código de uma app.

## 3. Onde cada arquivo fica

- `dataclasses/` só existe dentro de uma camada ou de `commons/` (raiz).

**DTO ou QueryObject?** Os dois são `dataclasses` e ficam em `dataclasses/`:

- **DTO** (*data transfer object*): objeto que carrega dados entre camadas, módulos ou sistemas externos. Ex.:
  `create_patient_dto.py` com a classe `CreatePatientDTO`. É sempre declarado em `dataclasses/`, nunca em outro arquivo.
- **QueryObject**: agrupa os parâmetros de uma consulta quando a função do repository cresce demais. Ex.:
  `find_patient_query_object.py` com a classe `FindPatientQueryObject`.

Regras do QueryObject:

- A classe termina em `QueryObject` e o arquivo, em `_query_object`.
- É exclusivo da camada `dataproviders` (repository): usecases e services não o criam nem o declaram.
- Pode ser declarado no próprio arquivo da query ou em `dataclasses/`.
- **Não pode ter regra de negócio, em hipótese alguma.** Um método de apoio ao próprio objeto é aceitável, mas a lógica
  de negócio fica em `services`.

## 4. Nomes

**Pastas e arquivos:** `snake_case` minúsculo.

**Arquivos, pelo local onde ficam:**

| Local                    | Sufixo                    | Exemplo                     |
|--------------------------|---------------------------|-----------------------------|
| `entrypoints/rest/`      | `_router`                 | `patient_router.py`         |
| `entrypoints/messaging/` | `_consumer`               | `sync_consumer.py`          |
| `usecases/`              | `_usecase`                | `create_patient_usecase.py` |
| `services/`              | `_service`                | `dose_service.py`           |
| `dataclasses/`           | `_dto` ou `_query_object` | `create_patient_dto.py`     |
| qualquer `schemas/`      | `_schema`                 | `patient_schema.py`         |

**Classes:**

- Arquivo `_dto` → classe termina em `DTO`; `_query_object` → `QueryObject`; `_schema` → `Schema`.
- Classe ORM termina em `Model` (ex.: `PatientModel`).
- Classes que começam com `_` são ignoradas.

**Uma função pública por arquivo** em `usecases/` e `dataproviders/` (exceto `dataclasses/`, `schemas/` e models ORM): o
arquivo `create_patient_usecase.py` expõe uma função, e o que for auxiliar começa com `_`.

## 5. Criando um bypass

Se uma regra não puder ser cumprida em algum ponto, é possível criar um bypass para ela no `[tool.check-structure]` do
`pyproject.toml` da app. O bypass deve ser, preferencialmente, temporário: existe até que o problema seja resolvido e,
então, é removido. Por isso, todo bypass leva uma justificativa (`reason`) ou um `TODO` dizendo quando sai.

Do mais restrito ao mais amplo:

- **Um import:** `[[tool.check-structure.exceptions]]` com `from`, `to` e `reason`.
- **Um arquivo ou pasta:** `[[tool.check-structure.path_exceptions]]` com `rule`, `path` (glob) e `reason`. Ex.:
  migrations do Alembic, cujo nome carrega o hash da revisão.
- **Uma regra inteira:** `disable = ["<id-da-regra>"]`.

Prefira sempre o mais restrito. Sintaxe completa e ids das regras:
[README da lib](../../packages/check-structure/README.md#configuração) para localizar o arquivo que contém a informação.

Durante a migração, as apps usam bypasses para descrever a estrutura que ainda têm, todos marcados com `TODO`:

- `modules_package` e `exclude_modules`: a app ainda não tem `modules/`.
- `layers`, `common_package` e `module_commons`: nomes no singular (`entrypoint`, `service`, `dataprovider`, `common`).
- `disable = ["root-folders"]`: a raiz ainda não tem o formato final.

Ao migrar uma app, remova esses bypasses e rode `make check-structure` até não restarem violações.
