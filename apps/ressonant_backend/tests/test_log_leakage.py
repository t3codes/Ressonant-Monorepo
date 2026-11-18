"""Regressão CYB-001 no pipeline real de log (common-errors + common-logs).

O log renderizado não pode conter o `input` de um erro de validação (senha, CPF)
nem o campo `exception`: o traceback do Pydantic carrega o `input` em claro.
"""

import json

import pytest
from common.errors import setup_exception_handlers
from common.logs import get_logger, setup_logging
from fastapi import FastAPI
from pydantic import BaseModel, Field
from starlette.testclient import TestClient

SENSITIVE_PASSWORD_MARKER = "senha-vazada-marker"
SENSITIVE_CPF_MARKER = "cpf-vazado-marker"


class JsonSettings:
    """Renderer JSON (ambiente != local) e nível INFO para o `warning` passar."""

    logger_level = "INFO"
    environment = "test"


class SensitivePayload(BaseModel):
    senha: str = Field(min_length=32)
    cpf: str = Field(pattern=r"^\d{3}\.\d{3}\.\d{3}-\d{2}$")


def _sensitive_body() -> dict[str, str]:
    return {"senha": SENSITIVE_PASSWORD_MARKER, "cpf": SENSITIVE_CPF_MARKER}


@pytest.fixture
def probe_client() -> TestClient:
    probe = FastAPI()
    setup_exception_handlers(probe)

    @probe.post("/probe-request")
    def probe_request(payload: SensitivePayload) -> dict[str, str]:
        return payload.model_dump()

    @probe.get("/probe-model")
    def probe_model() -> dict[str, str]:
        return SensitivePayload.model_validate(_sensitive_body()).model_dump()

    return TestClient(probe, raise_server_exceptions=False)


def _rendered_records(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    return [json.loads(line) for line in capsys.readouterr().out.strip().splitlines() if line]


def _assert_no_leak(capsys: pytest.CaptureFixture[str], event: str) -> None:
    records = _rendered_records(capsys)
    events = [record["message"] for record in records]
    assert event in events

    record = records[events.index(event)]
    assert record["level"] == "warning"
    assert "exception" not in record

    dumped = json.dumps(records)
    assert SENSITIVE_PASSWORD_MARKER not in dumped
    assert SENSITIVE_CPF_MARKER not in dumped


def test_request_validation_log_has_no_input_and_no_exception(
    capsys: pytest.CaptureFixture[str], probe_client: TestClient
) -> None:
    setup_logging(JsonSettings())
    capsys.readouterr()

    response = probe_client.post("/probe-request", json=_sensitive_body())

    assert response.status_code == 422
    assert SENSITIVE_PASSWORD_MARKER not in response.text
    assert SENSITIVE_CPF_MARKER not in response.text
    _assert_no_leak(capsys, "validation.request.rejected")


def test_model_validation_log_has_no_input_and_no_exception(
    capsys: pytest.CaptureFixture[str], probe_client: TestClient
) -> None:
    setup_logging(JsonSettings())
    capsys.readouterr()

    response = probe_client.get("/probe-model")

    assert response.status_code == 422
    assert SENSITIVE_PASSWORD_MARKER not in response.text
    assert SENSITIVE_CPF_MARKER not in response.text
    _assert_no_leak(capsys, "validation.model.rejected")


def test_json_pipeline_renders_exception_when_explicitly_requested(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Controle: o mesmo pipeline renderiza `exception` quando há `exc_info`.

    Sem isso a asserção de ausência acima poderia passar por o log não ser capturado.
    """
    setup_logging(JsonSettings())
    capsys.readouterr()

    log = get_logger("cyb001.control")
    try:
        raise ValueError(SENSITIVE_PASSWORD_MARKER)
    except ValueError:
        log.error("cyb001.control.failed", exc_info=True)

    (record,) = _rendered_records(capsys)
    assert record["level"] == "error"
    assert SENSITIVE_PASSWORD_MARKER in str(record["exception"])
