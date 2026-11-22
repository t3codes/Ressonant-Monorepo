import pytest
from app.modules.auth.schemas.dto import ConvidadoInput, RegistrationCreate
from pydantic import ValidationError
from tests.conftest import VALID_CPFS


def registration_payload(**overrides: object) -> dict[str, object]:
    """Payload aprovado em §5.1, com dados fictícios e CPF válido de teste."""
    payload: dict[str, object] = {
        "nome_completo": "João da Silva",
        "cargo": "Dono da Empresa",
        "email": "joao@example.com",
        "cpf": VALID_CPFS[0],
        "telefone": "(11) 98765-4321",
        "idade": 30,
        "senha": "senha-forte-1",
        "termos_contrato": True,
        "organizacao": {"nome": "Acme Ltda", "slug": "acme"},
        "plano_id": "equipe",
        "trial": True,
        "workspace_nome": "Acme Ltda",
        "equipe_inicial_nome": "Engenharia",
        "convidados": [],
    }
    payload.update(overrides)
    return payload


def error_paths(exc: ValidationError) -> set[str]:
    return {".".join(str(part) for part in err["loc"]) for err in exc.errors()}


def test_approved_registration_payload_is_accepted() -> None:
    dto = RegistrationCreate.model_validate(registration_payload())

    assert dto.nome_completo == "João da Silva"
    assert dto.email == "joao@example.com"
    assert dto.cpf == VALID_CPFS[0]
    assert dto.plano_id == "equipe"
    assert dto.trial is True
    assert dto.organizacao.slug == "acme"
    assert dto.convidados == []


def test_nome_completo_with_single_word_fails() -> None:
    with pytest.raises(ValidationError) as exc:
        RegistrationCreate.model_validate(registration_payload(nome_completo="João"))

    assert "nome_completo" in error_paths(exc.value)


def test_organizacao_slug_with_space_fails() -> None:
    with pytest.raises(ValidationError) as exc:
        RegistrationCreate.model_validate(
            registration_payload(organizacao={"nome": "Acme Ltda", "slug": "acme ltda"})
        )

    assert "organizacao.slug" in error_paths(exc.value)


def test_plano_id_outside_enum_fails() -> None:
    with pytest.raises(ValidationError) as exc:
        RegistrationCreate.model_validate(registration_payload(plano_id="enterprise"))

    assert "plano_id" in error_paths(exc.value)


def test_trial_false_fails() -> None:
    with pytest.raises(ValidationError) as exc:
        RegistrationCreate.model_validate(registration_payload(trial=False))

    assert "trial" in error_paths(exc.value)


def test_duplicate_convidado_emails_are_rejected_case_insensitively() -> None:
    with pytest.raises(ValidationError) as exc:
        RegistrationCreate.model_validate(
            registration_payload(
                convidados=[
                    {"email": "Ana@Example.com"},
                    {"email": "ana@example.com"},
                ]
            )
        )

    assert "convidados" in error_paths(exc.value)


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        RegistrationCreate.model_validate(registration_payload(campo_desconhecido=1))

    assert "campo_desconhecido" in error_paths(exc.value)


def test_termos_contrato_false_fails() -> None:
    with pytest.raises(ValidationError) as exc:
        RegistrationCreate.model_validate(registration_payload(termos_contrato=False))

    assert "termos_contrato" in error_paths(exc.value)


def test_identity_validators_from_user_register_are_reused() -> None:
    dto = RegistrationCreate.model_validate(
        registration_payload(email="JOAO@EXAMPLE.COM", cpf="529.982.247-25")
    )

    assert dto.email == "joao@example.com"
    assert dto.cpf == VALID_CPFS[0]


def test_convidado_defaults_to_member_role() -> None:
    convidado = ConvidadoInput.model_validate({"email": "maria@example.com"})

    assert convidado.role == "member"
    assert convidado.nome is None
