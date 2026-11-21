"""Rotas de upload de imagem."""

from app.modules.auth.deps import CurrentUser
from app.modules.image_upload.usecases.services import ImageUploadService
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

router = APIRouter(prefix="/upload", tags=["upload"])


def get_image_service() -> ImageUploadService:
    return ImageUploadService()


@router.post("/image", status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    user: CurrentUser = CurrentUser,
    service: ImageUploadService = Depends(get_image_service),
):
    """Faz upload de uma imagem.

    Validações:
    - Tipo: image/jpeg, image/png, image/webp
    - Tamanho máximo: 5 MB

    Retorna a URL da imagem enviada.
    """
    content = await file.read()
    try:
        result = service.upload(
            content, file.filename or "image", file.content_type or "application/octet-stream"
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return {
        "url": result.url,
        "content_type": result.content_type,
        "size_bytes": result.size_bytes,
        "storage_provider": result.storage_provider,
    }
