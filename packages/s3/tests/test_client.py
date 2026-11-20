import pytest
from common.s3 import S3ObjectStore


class FakeS3Client:
    def __init__(self) -> None:
        self.put_args: dict[str, object] | None = None

    def put_object(self, **kwargs: object) -> None:
        self.put_args = kwargs

    def generate_presigned_url(
        self,
        operation: str,
        *,
        Params: dict[str, str],
        ExpiresIn: int,
    ) -> str:
        assert operation == "get_object"
        assert Params["Bucket"] == "unit-test-bucket"
        assert ExpiresIn == 600
        return "https://s3.example.test/signed-object"


def test_upload_bytes_stores_content_and_returns_signed_url() -> None:
    client = FakeS3Client()
    store = S3ObjectStore("unit-test-bucket", client=client)

    url = store.upload_bytes(
        "images/avatar.png",
        b"png-content",
        "image/png",
        expires_in=600,
    )

    assert url == "https://s3.example.test/signed-object"
    assert client.put_args == {
        "Bucket": "unit-test-bucket",
        "Key": "images/avatar.png",
        "Body": b"png-content",
        "ContentType": "image/png",
    }


def test_upload_bytes_rejects_absolute_or_parent_path_keys() -> None:
    store = S3ObjectStore("unit-test-bucket", client=FakeS3Client())

    with pytest.raises(ValueError):
        store.upload_bytes("../private.txt", b"data", "text/plain")
    with pytest.raises(ValueError):
        store.upload_bytes("/private.txt", b"data", "text/plain")


def test_bucket_is_required() -> None:
    with pytest.raises(ValueError, match="AWS_S3_BUCKET"):
        S3ObjectStore("")
