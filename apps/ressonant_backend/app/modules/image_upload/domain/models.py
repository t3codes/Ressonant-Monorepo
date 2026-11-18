"""Modelos de domínio para upload de imagem."""

from dataclasses import dataclass


@dataclass
class ImageUploadResult:
    """Resultado do upload de imagem."""

    url: str
    content_type: str
    size_bytes: int
    storage_provider: str  # "minio" | "local"


@dataclass
class ImageValidationError:
    """Erro de validação de imagem."""

    message: str
    code: str


# Constantes de validação
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
