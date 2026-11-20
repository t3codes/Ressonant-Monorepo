from app.modules.image_upload.usecases.services import ImageUploadService
from tests.conftest import login, make_user


class FakeImageStorage:
    def __init__(self) -> None:
        self.uploaded: tuple[str, bytes, str] | None = None

    def upload_bytes(
        self, key: str, content: bytes, content_type: str, *, expires_in: int = 3600
    ) -> str:
        self.uploaded = (key, content, content_type)
        return "https://s3.example.test/presigned-image"


def _create_user_and_headers(client, session_factory, email="ana@ressonant.dev", cpf="52998224725"):
    make_user(session_factory, email=email, cpf=cpf)
    return login(client, email)


def test_upload_image_valid(client, session_factory):
    headers = _create_user_and_headers(client, session_factory)
    # Criar uma imagem PNG minima (1x1 pixel)
    png_data = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        b"\x90wS\xde"
        b"\x00\x00\x00\tpHYs"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x01\x00\x9c\xba"
        b"\x00\x00\x00\x0cIDAT"
        b"\x08\xd7c\xf8\xff\xff\x3f\x03\x00\x00\x02\x04\x01\xe2"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    r = client.post(
        "/upload/image", files={"file": ("test.png", png_data, "image/png")}, headers=headers
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "url" in body
    assert body["content_type"] == "image/png"
    assert body["size_bytes"] > 0


def test_upload_image_invalid_type(client, session_factory):
    headers = _create_user_and_headers(client, session_factory)
    r = client.post(
        "/upload/image", files={"file": ("test.txt", b"texto", "text/plain")}, headers=headers
    )
    assert r.status_code == 400, r.text


def test_upload_image_requires_auth(client):
    png_data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    )
    r = client.post("/upload/image", files={"file": ("test.png", png_data, "image/png")})
    assert r.status_code != 201, f"Deveria rejeitar sem auth: {r.status_code}"


def test_image_service_uses_injected_s3_storage() -> None:
    storage = FakeImageStorage()
    service = ImageUploadService(storage_client=storage)

    result = service.upload(b"png-content", "photo.png", "image/png")

    assert result.storage_provider == "s3"
    assert result.url == "https://s3.example.test/presigned-image"
    assert storage.uploaded is not None
    assert storage.uploaded[0].startswith("images/")
    assert storage.uploaded[1:] == (b"png-content", "image/png")
