"""Serviço de upload de imagem com validação de tamanho e tipo."""

import os
import uuid
from pathlib import Path
from typing import Optional

from app.modules.image_upload.domain.models import (
    ImageUploadResult,
    ImageValidationError,
    ALLOWED_IMAGE_CONTENT_TYPES,
    MAX_IMAGE_SIZE_BYTES,
)


class ImageUploadService:
    """Serviço responsável pelo upload e validação de imagens.

    Preparado para integração com MinIO. Enquanto o MinIO não estiver
    configurado, armazena localmente em uploads/.
    """

    def __init__(self, storage_provider: str = "local", upload_dir: str = "/tmp/ressonant_uploads"):
        self.storage_provider = storage_provider
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def validate_image(self, content_type: str, size_bytes: int) -> Optional[ImageValidationError]:
        """Valida tipo e tamanho da imagem.

        Returns None se válido, ou ImageValidationError se inválido.
        """
        if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            return ImageValidationError(
                message=f"Tipo de arquivo não permitido: {content_type}. "
                f"Tipos aceitos: {', '.join(sorted(ALLOWED_IMAGE_CONTENT_TYPES))}",
                code="INVALID_CONTENT_TYPE",
            )
        if size_bytes > MAX_IMAGE_SIZE_BYTES:
            max_mb = MAX_IMAGE_SIZE_BYTES / (1024 * 1024)
            return ImageValidationError(
                message=f"Arquivo muito grande: {size_bytes / (1024 * 1024):.1f}MB. "
                f"Limite: {max_mb:.0f}MB",
                code="FILE_TOO_LARGE",
            )
        return None

    def upload(self, file_content: bytes, filename: str, content_type: str) -> ImageUploadResult:
        """Faz upload da imagem após validação.

        Raises ImageValidationError se a validação falhar.
        """
        error = self.validate_image(content_type, len(file_content))
        if error:
            raise ValueError(error.message)

        # Gerar nome único para o arquivo
        file_extension = Path(filename).suffix.lower()
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = self.upload_dir / unique_filename

        # Salvar arquivo localmente (substituir por MinIO quando configurado)
        with open(file_path, "wb") as f:
            f.write(file_content)

        url = f"/uploads/{unique_filename}"

        return ImageUploadResult(
            url=url,
            content_type=content_type,
            size_bytes=len(file_content),
            storage_provider=self.storage_provider,
        )
