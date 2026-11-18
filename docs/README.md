# Documentação do monorepo

Ponto de partida para quem chega ao time. Comece pelos [primeiros passos](#primeiros-passos), na ordem: ao final, você
terá acesso aos sistemas, a máquina pronta, a visão geral do produto e dos ambientes, e saberá como uma mudança vai do
código à produção. O restante está organizado pelo momento em que é útil: desenvolver, rodar e entregar, operar.

> **Refatoração em andamento.** As apps estão sendo migradas para os padrões descritos aqui. Dependendo do momento da
> leitura, parte do código ainda segue o formato antigo e diverge da documentação. Nesse caso, a documentação descreve
> o formato alvo: código novo segue a documentação, e o código antigo é migrado nas tarefas de refatoração.

## Primeiros passos

1. **[Acessos](to-do)** — os acessos necessários para trabalhar no projeto e como solicitar cada um.
2. **[Setup da máquina](to-do)** — ferramentas, commits assinados, hooks e checkers.
3. **[Como contribuir](to-do)** — o fluxo de uma mudança: branch, commit, pull request e review.
4. **[Arquitetura](to-do)** — as apps do monorepo, como se comunicam e de quais serviços externos dependem.
5. **[Domínio e glossário](to-do)** — os termos do negócio que aparecem no código.
6. **[Ambientes](to-do)** — os ambientes do projeto, para que serve cada um e como testar nele.

## Desenvolver

- **[Estrutura das apps](guides/app-structure.md)** — pastas, camadas, direção dos imports e nomes.
- **[Testes unitários](guides/unit-tests.md)** — como testar cada camada isolada, com mocks.
- **[Testes integrados](guides/integration-tests.md)** — o que cobrir contra uma app deployada e o fluxo com as skills
  de planejamento e implementação.
- **[Banco de dados e migrations](to-do)** — como criar e rodar uma migration e o que evitar.
- **[Contratos de API](to-do)** — onde está a especificação das rotas, como são versionadas e o que é breaking change.
- **[Uso de IA no repositório](to-do)** — os recursos de IA configurados no repositório e quando usar cada um.

## Rodar e entregar

- **[Ambiente local](docker-compose.md)** — como subir as apps com Docker Compose.
- **[CI/CD](ci-cd.md)** — os workflows de lint, teste e deploy, e como uma versão chega a cada ambiente.
- **[Segredos](to-do)** — onde ficam os segredos, como ler e adicionar um.

## Operar

- **[Observabilidade](to-do)** — dashboards, logs, traces e alertas, e como investigar um problema a partir deles.
- **[Incidentes e rollback](to-do)** — o que fazer quando algo quebra em produção.

## Decisões (ADRs)

Uma ADR (*Architecture Decision Record*) registra uma decisão técnica com o contexto e as alternativas da época, para
que ela não seja rediscutida nem desfeita por quem não estava lá. Antes de questionar um padrão que parece estranho,
procure a ADR dele.

- **[Decisões do monorepo](adrs/)** — valem para todas as apps.
- **Decisões de uma app** — ficam em `apps/<app>/docs/adrs/`.

Para registrar uma decisão nova, copie o [`0000-template.md`](adrs/0000-template.md) da pasta correspondente.

## Além de `docs/`

Como cada app ou lib funciona (responsabilidade, como subir, variáveis de ambiente) está no README dela, em
`apps/<app>/` ou `packages/<lib>/`.
