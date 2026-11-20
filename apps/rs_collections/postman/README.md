# Collection Postman do Ressonant

## Importação

Importe `import-json/ressonant-backend.postman_collection.json` no Postman e importe um ambiente de `import-json/` ou use os ambientes sincronizados em `environments/`. No ambiente Local, ajuste `baseUrl` se necessário. Para homologação, informe uma conta de teste em `email` e `senha`; não use credenciais de produção.

## O que foi melhorado

- 63 operações HTTP únicas, alinhadas a `apps/ressonant_backend/openapi.json`, incluindo criar/listar/consultar conversas e logout.
- Cada request tem teste automatizado do status de sucesso declarado na OpenAPI; respostas JSON são verificadas e IDs de criação são salvos no ambiente (por exemplo, `workspaceId`, `channelId`, `messageId` e `conversationId`). Login captura `accessToken`; `/auth/me` propaga o `userId` para requests dependentes.
- Corrigidos campos fora do schema atual em criação de canais e emails, e incluído `user_id` como query param no request de adicionar membro a canal.
- Os folders estão ordenados para favorecer dependências e o logout fica por último.

## Execução segura

Na collection Runner, use o ambiente Local. `autoRegisterTestUser=true` cria uma conta local efêmera com email/CPF únicos antes do login; use isso apenas em banco local descartável. O ambiente de homologação define `skipRegister=true` e `autoRegisterTestUser=false`, portanto usa a conta de teste configurada sem tentar registrar usuário.

Para habilitar operações administrativas (requests em Users), defina `runAdminOperations=true` e use uma conta de teste com a permissão apropriada. Elas ficam ignoradas por padrão. Requests DELETE também são ignorados; para executá-los deliberadamente, defina `allowDestructive=true`. Upload é ignorado sem `filePath`; informe um caminho local acessível ao Postman/Newman para habilitá-lo.

A coleção não é totalmente isolada por request: execute em ordem ou selecione requests depois de preparar os IDs/credenciais necessários. Requests de escrita criam dados. Logout invalida o token e está no último folder.
