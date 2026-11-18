# 2. Data UTC nas Folhas LME da Resposta de Criação

## Contexto

A criação de prescrição com bloco `lme` devolve, em
`lme_response[].ressonants.<print_type>[]`, uma folha por grupo de medicamentos do
tratamento. Cada folha traz `ressonant_date` como data pura (`YYYY-MM-DD`). A data da
emissão é gravada no banco como `timestamp` sem fuso, em UTC, e a resposta tira dela o dia
do calendário UTC.

O PDF da mesma folha imprime a data em `America/Sao_Paulo`. Por isso, numa emissão depois
das 21:00 no horário de Brasília, a resposta traz o dia seguinte e o PDF traz o dia correto.
As filhas em `apart_ressonants` não têm esse problema: devolvem o datetime completo, e o
cliente converte para o fuso local.

O legado se comporta da mesma forma. Em `formatLmePrescRes` (maagizo, `lme_svc.go`), a data
da folha é `RessonantDate.Format(time.DateOnly)`, isto é, o dia UTC. O contrato desta
resposta espelha o `lmeResponse` do legado, e os clientes exibem o valor como ele chega.

## Decisão

Nós manteremos `ressonant_date` das folhas LME como o dia do calendário UTC, em paridade
com o legado. O schema `LmeSheetResponse` aponta para esta ADR na linha que faz a conversão.

## Consequências

Clientes que migram do legado recebem exatamente a data que já recebiam, sem ajuste. Em
contrapartida, emissões entre 21:00 e 23:59 no horário de Brasília mostram na resposta uma
data um dia à frente da impressa no PDF.

Para mudar isso depois, há dois caminhos. O primeiro é converter o instante UTC para
`America/Sao_Paulo` antes de tirar a data, alinhando a resposta ao PDF sem mudar o formato
do campo. O segundo é devolver o datetime completo, como as demais filhas, e deixar a
conversão para o cliente, o que muda o formato do campo e exige combinar com os
consumidores. Qualquer dos dois é mudança de contrato visível e pede card próprio.
