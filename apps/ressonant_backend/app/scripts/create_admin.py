"""Cria (ou promove) o primeiro administrador.

Uso: ADMIN_EMAIL=... ADMIN_PASSWORD=... ADMIN_CPF=... python -m app.scripts.create_admin
"""

import os
import sys

from app.common.security import hash_password
from app.database.engine import get_session_factory
from app.user.models import User
from app.user.repository import UserRepository
from app.user.schemas import is_valid_cpf


def main() -> int:
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    cpf = "".join(ch for ch in os.getenv("ADMIN_CPF", "") if ch.isdigit())
    if not email or len(password) < 8 or not is_valid_cpf(cpf):
        print("Defina ADMIN_EMAIL, ADMIN_PASSWORD (min. 8) e ADMIN_CPF válido.", file=sys.stderr)
        return 1

    with get_session_factory()() as db:
        repo = UserRepository(db)
        if repo.get_by_email(email):
            print("Já existe um usuário com esse e-mail; nada foi alterado.", file=sys.stderr)
            return 1
        repo.add(
            User(
                email=email,
                senha_hash=hash_password(password),
                cpf=cpf,
                idade=18,
                termos_contrato=True,
                telefone=os.getenv("ADMIN_TELEFONE", "11999999999"),
                status_ativo=True,
                interno_adm=True,
            )
        )
        repo.commit()
    print(f"Administrador {email} criado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
