"""DTOs de upload de imagem."""

from pydantic import BaseModel


class ImageUploadResponse(BaseModel):
    url: str
    content_type: str
    size_bytes: int
    storage_provider: str


class ImageValidationConfig(BaseModel):
    max_size_mb: float = 5.0
    allowed_content_types: list[str] = ["image/jpeg", "image/png", "image/webp"]
