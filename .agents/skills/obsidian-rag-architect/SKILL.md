---
name: obsidian-rag-architect
description: Arquitetura de RAG (Retrieval-Augmented Generation) conectada a um cofre Obsidian para o Ressonant. Use ao projetar ou implementar ingestão de Markdown, parsing de YAML frontmatter, wikilinks, backlinks e headings, chunking, embeddings, busca vetorial/híbrida, reranking, indexação incremental, sincronização do vault, avaliação de recuperação e context engineering para agentes. Nada disso está implementado hoje; a skill orienta o projeto sem presumir decisões ainda não tomadas.
metadata:
  scope: rag-obsidian
  language: pt-BR
---

# obsidian-rag-architect

## Estado real

| Item | Estado |
|---|---|
| Conceito: RAG com cofre Obsidian como fonte contextual de agentes | **Planejado** |
| Código, tabelas, migrations, dependências, endpoints de RAG | **Não existem** |
| Decisões de vector store, modelo de embeddings, reranker, onde o vault vive e como sincroniza | **Em aberto** |
| PostgreSQL 15 | Existe (pgvector **não** está habilitado: a imagem é `postgres:15-alpine`) |

Antes de propor código, confirme no repo (`grep`, `ls apps packages`) se algo mudou. **Nunca** apresente uma opção abaixo como decisão tomada: apresente alternativas com trade-offs e peça a decisão ao usuário.

## Princípios (valem qualquer que seja a stack)

1. **O vault é a fonte da verdade, só leitura.** O pipeline lê `.md`; nunca escreve, move ou apaga notas. Não dependa do app Obsidian estar aberto (a skill `obsidian-cli` exige o app; o pipeline lê arquivos).
2. **Preserve estrutura e metadados**: cada chunk carrega caminho da nota, título, caminho de headings (`H1 > H2 > H3`), frontmatter relevante (tags, aliases, datas), links de saída e hash do conteúdo.
3. **Chunking por heading**, respeitando limite de tokens: seção pequena fica inteira; seção grande divide por parágrafo com sobreposição curta. Nunca corte dentro de bloco de código, tabela, callout ou lista. Prefixe o chunk com o caminho de headings.
4. **Links são sinal**: extraia wikilinks (`[[Nota]]`, `[[Nota#Heading]]`, `[[Nota#^bloco]]`, `[[Nota|alias]]`), embeds (`![[...]]`) e tags (`#tag`); resolva por nome/alias; calcule backlinks invertendo o grafo. Link para nota inexistente é dado, não erro.
5. **Indexação incremental**: identifique a nota por caminho + hash de conteúdo; reindexe só o que mudou, trate renomeação e exclusão (remova chunks órfãos), e registre a versão do modelo de embedding junto ao vetor (trocar o modelo exige reindexar tudo).
6. **Recuperação híbrida** costuma superar a busca puramente vetorial em vaults (nomes de nota, siglas, códigos): combine busca léxica e vetorial com fusão (por exemplo RRF) e, se a latência permitir, reranking. Meça antes de adicionar complexidade.
7. **Avalie com dados**: monte um conjunto de perguntas com notas esperadas (golden set) e acompanhe recall@k, MRR/nDCG e taxa de "sem resposta". Mudança de chunking, modelo ou fusão só entra com métrica melhor.
8. **Respeite permissões**: o que um agente recupera deve obedecer a quem pode ler aquela nota (futuro: workspace/canal). Não misture vaults de usuários no mesmo índice sem filtro por proprietário.

## Segurança: injeção indireta de prompt

Conteúdo de notas vira contexto de LLM. Trate-o como **dado não confiável**: delimite o contexto recuperado, instrua o modelo a não obedecer instruções contidas nele, limite as ferramentas disponíveis a agentes que leem o vault, não exponha segredos em notas ao contexto (filtre padrões de credencial na ingestão) e registre a origem (caminho/heading) de cada trecho citado.

## Decisões em aberto (apresente alternativas, não escolha sozinho)

| Decisão | Alternativas típicas | Considerar |
|---|---|---|
| Vector store | pgvector no PostgreSQL existente · serviço dedicado (Qdrant, Milvus etc.) | operar um banco só vs. escala e recursos de busca; pgvector exigiria trocar/estender a imagem do Postgres |
| Busca léxica | `tsvector`/BM25 no Postgres · motor externo | simplicidade vs. qualidade |
| Embeddings | modelo local aberto · API de fornecedor · NVIDIA NIM | custo, latência, privacidade, idioma (PT-BR + inglês), dimensão do vetor |
| Reranker | nenhum · cross-encoder local · serviço | ganho medido vs. latência |
| Origem do vault | diretório montado · repositório Git · sync | como detectar mudanças e quem é o dono |
| Onde roda a ingestão | job no backend · worker separado · processo agendado | combina com a arquitetura de apps do monorepo (`architecture-guard`) |

Qualquer implementação seguirá as regras do monorepo: nova app/pacote só com autorização (`architecture-guard`), código Python no padrão do backend (`python-backend-specialist`), migrations revisadas, dependências justificadas, testes e `openapi.json` atualizado (`qa-and-openapi`), telemetria via `common-telemetry` (`devops-observability`).

## Skills relacionadas

- **`obsidian-markdown`** (instalada, de kepano): sintaxe Obsidian Flavored Markdown; use como referência de parsing de wikilinks, embeds, callouts e properties.
- **`nvidia-skill-finder`** (instalada, NVIDIA): use **sob demanda**, só quando o usuário optar por tecnologias NVIDIA (NIM, embeddings e rerankers NVIDIA, NeMo Retriever, RAG da NVIDIA) ou pedir conhecimento oficial NVIDIA. Ela consulta o catálogo ao vivo (`npx skills add nvidia/skills --list`) e **recomenda; não instale nada sem aprovação do usuário**. As skills do catálogo são complementares: o Ressonant **não depende** delas. Confira o catálogo atual antes de citar nomes (hoje existem, por exemplo, `nemo-retriever` e `rag-blueprint`, que exigem GPU/serviços NVIDIA ou o RAG Blueprint; podem não servir a um índice em Postgres).
- **`supabase-postgres-best-practices`**: índices, paginação e pooling se o armazenamento for Postgres.
- Skills externas de RAG genéricas (`rag-implementation`, `hybrid-search-implementation`) **não** estão instaladas; se o usuário quiser, podem ser adicionadas depois.

## Como trabalhar

1. Esclareça o objetivo e as restrições (tamanho do vault, idioma, latência, privacidade, onde roda).
2. Leia o que já existe no repo; liste decisões em aberto relevantes e recomende, com justificativa, a opção mais simples que atende.
3. Proponha o pipeline em etapas pequenas e verificáveis: parser → chunker → armazenamento → recuperação → avaliação. Entregue o parser/chunker com testes sobre notas de exemplo **antes** de embeddings.
4. Nunca baixe dados de vault reais para o repositório nem registre conteúdo de notas em logs.
