# 1. Snake Case Como Contrato HTTP Padrão

## Contexto

O monorepo expõe APIs HTTP no `ressonant-backend` e no `ressonant-bff`. Os nomes das
chaves no fio (query params, path params compostos, request body e response body) nasceram
misturados: alguns endpoints já aceitam só snake_case no body, outros ainda documentam
camelCase como nome canônico, e vários schemas Pydantic expõem os dois via `AliasChoices`,
`validation_alias`, `serialization_alias` ou `Query(alias=...)`.

Essa mistura custa caro. OpenAPI, testes de contrato e consumidores passam a tratar o alias
como se fosse o nome oficial. Endpoints novos copiam o precedente mais próximo, não uma
regra única. Docs vivos descrevem dual-casing como se fosse o contrato desejado, e não como
compatibilidade temporária.

O `ressonant-auth` não desenha contrato JSON nosso: é Keycloak. Sistemas que consumimos
(Basemed, SSO e equivalentes) também trazem o casing que já têm. Snapshots JSONB persistidos
no maagizo e valores de enum/discriminador (`freeText`, `simpleTwoCopy`, `commercial`) já
existem em camelCase e não fazem parte desta decisão de **nome de chave**.

## Decisão

Nós trataremos snake_case como o único nome canônico das chaves HTTP **novas** que este
monorepo expõe no `ressonant-backend` e no `ressonant-bff`. Isso vale para query
params, path params compostos, chaves de request body e chaves de response body.

Esta decisão vale **daqui para frente**. Ela não autoriza mudar comportamento, OpenAPI,
aliases ou testes de contrato que já existem. Funções e endpoints que hoje aceitam ou
emitem camelCase continuam como estão: o casing atual não é débito a “corrigir” nesta
ADR, nem em review de outro card.

Em endpoint **novo**, nós não adicionaremos `validation_alias`, `serialization_alias`,
`alias` de `Field` nem `Query(alias=...)` em camelCase. OpenAPI e testes de contrato
desse endpoint usarão o nome snake_case.

Em contrato **já publicado**, aliases e chaves camelCase existentes permanecem. Nós não
os removeremos, não os converteremos e não adicionaremos um alias camelCase novo. Qualquer
migração de legado exige um card próprio — não nasce de review nem desta ADR.

Nós não aplicaremos esta decisão ao `ressonant-auth`, a contratos de terceiros que
apenas consumimos, a snapshots JSONB persistidos no maagizo, nem aos **valores** de
enum/discriminador. Nesses casos o dataprovider traduz; o nome da chave HTTP que nós
exponemos continua snake_case.

## Consequências

Docs vivos, READMEs e fontes lidas por agentes passam a apontar esta ADR. Review local
e CodeRabbit flagam alias camelCase **somente quando o diff introduz** um em contrato
novo. Código camelCase pré-existente, mesmo que apareça num arquivo tocado por outro
motivo, não é achado e não vira pedido de refatoração.

Endpoints novos ficam previsíveis para quem gera cliente, escreve teste ou lê o OpenAPI.
Endpoints antigos continuam aceitando e emitindo exatamente o que já aceitam e emitem.
Quem abrir um endpoint novo copiando um schema legado com `AliasChoices` camelCase
estará fora desta decisão.

A persistência compartilhada e os valores de enum não mudam. Quem persistir JSONB no
maagizo ou aceitar `type: "freeText"` não precisa converter esses valores para snake_case
por causa desta ADR.
