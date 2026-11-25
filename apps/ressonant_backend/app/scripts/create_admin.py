"""Bootstrap idempotente do primeiro administrador.

Uso: ADMIN_EMAIL=... ADMIN_PASSWORD=... ADMIN_CPF=... python -m app.scripts.create_admin
ADMIN_NAME e ADMIN_TELEFONE são opcionais.
"""

import sys

from app.common.security import hash_password
from app.config.settings import get_settings
from app.database.engine import get_session_factory
from app.user.models import User
from app.user.repository import UserRepository
from app.user.schemas import is_valid_cpf

DEFAULT_TELEFONE = "11999999999"
# Valores públicos do .env.example: nunca aceitos como credencial de superuser real.
PLACEHOLDER_EMAIL = "admin@empresa.com"
PLACEHOLDER_PASSWORD = "ChangeMe123!"


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def main() -> int:
    settings = get_settings()
    email = (settings.admin_email or "").strip().lower()
    password = settings.admin_password.get_secret_value() if settings.admin_password else ""
    cpf = _digits(settings.admin_cpf or "")
    if (
        not email
        or email == PLACEHOLDER_EMAIL
        or len(password) < 8
        or password.strip() == PLACEHOLDER_PASSWORD
        or not is_valid_cpf(cpf)
    ):
        print("Variáveis de bootstrap ausentes ou inválidas.", file=sys.stderr)
        return 1

    with get_session_factory()() as db:
        repo = UserRepository(db)
        user = repo.get_by_email(email)
        if user is None:
            name = settings.admin_name.strip() if settings.admin_name else None
            telefone = (
                settings.admin_telefone.strip() if settings.admin_telefone else DEFAULT_TELEFONE
            )
            repo.add(
                User(
                    email=email,
                    senha_hash=hash_password(password),
                    cpf=cpf,
                    idade=18,
                    termos_contrato=True,
                    telefone=telefone or DEFAULT_TELEFONE,
                    status_ativo=True,
                    interno_adm=True,
                    name=name or None,
                )
            )
            repo.commit()
        else:
            if _digits(user.cpf or "") != cpf:
                print("Bootstrap abortado: divergência de CPF.", file=sys.stderr)
                return 1
            user.status_ativo = True
            user.interno_adm = True
            repo.commit()

    print("Bootstrap concluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
