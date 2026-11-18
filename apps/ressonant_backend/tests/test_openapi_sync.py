import json
from pathlib import Path

from app.main import app

SPEC = Path(__file__).resolve().parents[1] / "openapi.json"


def test_committed_openapi_is_up_to_date() -> None:
    committed = json.loads(SPEC.read_text())
    assert committed == json.loads(json.dumps(app.openapi())), (
        "OpenAPI desatualizado: rode `make export-openapi` (e regenere as collections Postman)"
    )
