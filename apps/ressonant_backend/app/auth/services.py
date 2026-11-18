from app.auth.tokens import create_access_token
from app.common.exceptions import invalid_credentials
from app.common.security import verify_dummy, verify_password
from app.user.repository import UserRepository


class AuthService:
    def __init__(self, repository: UserRepository) -> None:
        self._repo = repository

    def login(self, email: str, senha: str) -> tuple[str, int]:
        user = self._repo.get_by_email(email.lower())
        if user is None:
            verify_dummy(senha)
            raise invalid_credentials()
        # Mesma resposta para senha errada e conta inativa: não revela o estado da conta.
        if not verify_password(senha, user.senha_hash) or not user.status_ativo:
            raise invalid_credentials()
        return create_access_token(user.id)
