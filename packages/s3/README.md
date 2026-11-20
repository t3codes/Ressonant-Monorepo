# common-s3

Cliente compartilhado para armazenar objetos via AWS S3 ou serviços compatíveis. O código consumidor pode injetar um cliente compatível em `S3ObjectStore` para testes e configurações especiais.

## Configuração

- `AWS_S3_BUCKET` (obrigatória quando S3 está habilitado)
- `AWS_S3_REGION` (opcional; padrão `us-east-1`)
- `AWS_S3_ENDPOINT_URL` (opcional; configure para LocalStack ou outro emulador)
- `AWS_ACCESS_KEY_ID` e `AWS_SECRET_ACCESS_KEY` são obtidas pelo provider chain padrão do boto3 e não devem ser gravadas em arquivos versionados.

`S3ObjectStore.from_env()` cria o cliente. `upload_bytes(key, content, content_type)` envia o objeto e retorna uma URL pré-assinada temporária de leitura; a aplicação é responsável por usar chaves imprevisíveis e validar conteúdo/tamanho.

Os testes unitários usam um cliente de protocolo compatível e não alegam validar AWS real ou LocalStack. Para isso, configure um endpoint de teste isolado e execute testes de integração próprios.
