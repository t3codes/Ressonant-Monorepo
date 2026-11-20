"""Cliente S3 pequeno e reutilizável para os apps do workspace."""

import os
from typing import Any


class S3ObjectStore:
    """Armazena objetos em AWS S3 ou em endpoints compatíveis, como LocalStack."""

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        region_name: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not bucket.strip():
            raise ValueError("AWS_S3_BUCKET deve ser configurado")
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.region_name = region_name or "us-east-1"
        if client is None:
            import boto3

            client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                region_name=self.region_name,
            )
        self._client = client

    @classmethod
    def from_env(cls) -> "S3ObjectStore":
        """Cria o cliente a partir das variáveis padrão AWS_S3_* e credenciais AWS."""
        bucket = os.getenv("AWS_S3_BUCKET", "").strip()
        if not bucket:
            raise ValueError("AWS_S3_BUCKET deve ser configurado para habilitar S3")
        return cls(
            bucket,
            endpoint_url=os.getenv("AWS_S3_ENDPOINT_URL") or None,
            region_name=os.getenv("AWS_S3_REGION", "us-east-1"),
        )

    def upload_bytes(
        self,
        key: str,
        content: bytes,
        content_type: str,
        *,
        expires_in: int = 3600,
    ) -> str:
        """Envia bytes e devolve URL pré-assinada de leitura temporária."""
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise ValueError("A chave S3 deve ser um caminho relativo seguro")
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        return str(
            self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        )
