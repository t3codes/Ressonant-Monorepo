from app.common.exceptions import ConflictException
from app.common.security import hash_password
from app.modules.user.dataproviders.repository import UserRepository
from app.modules.user.domain.models import User
from app.modules.user.schemas.dto import UserCreate, UserRegister, UserUpdate
from common.errors import ExceptionData, NotFoundException
from sqlalchemy.exc import IntegrityError


def _not_found() -> NotFoundException:
    return NotFoundException(
        ExceptionData(message="Usuário não encontrado", error_code="USER_NOT_FOUND"),
        is_expected=True,
    )


def _conflict(message: str, code: str) -> ConflictException:
    return ConflictException(ExceptionData(message=message, error_code=code), is_expected=True)


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self._repo = repository

    def add_user(
        self,
        payload: UserRegister,
        *,
        status_ativo: bool = True,
        interno_adm: bool = False,
    ) -> User:
        """Prepara o usuário na Session; a transação fica com quem chama."""
        if self._repo.exists_by_email_or_cpf(payload.email, payload.cpf):
            raise _conflict("E-mail ou CPF já cadastrado", "USER_ALREADY_EXISTS")
        user = User(
            email=payload.email,
            senha_hash=hash_password(payload.senha),
            cpf=payload.cpf,
            idade=payload.idade,
            termos_contrato=payload.termos_contrato,
            telefone=payload.telefone,
            status_ativo=status_ativo,
            interno_adm=interno_adm,
        )
        self._repo.add(user)
        return user

    def register(self, payload: UserRegister) -> User:
        """Cadastro público: sempre usuário comum e ativo."""
        try:
            user = self.add_user(payload)
            self._repo.commit()
        except IntegrityError:
            self._repo.rollback()
            raise _conflict("E-mail ou CPF já cadastrado", "USER_ALREADY_EXISTS") from None
        return user

    def create(self, payload: UserCreate) -> User:
        try:
            user = self.add_user(
                payload, status_ativo=payload.status_ativo, interno_adm=payload.interno_adm
            )
            self._repo.commit()
        except IntegrityError:
            self._repo.rollback()
            raise _conflict("E-mail ou CPF já cadastrado", "USER_ALREADY_EXISTS") from None
        return user

    def get(self, user_id: str) -> User:
        user = self._repo.get_by_id(user_id)
        if user is None:
            raise _not_found()
        return user

    def list(self, skip: int, limit: int, status_ativo: bool | None) -> tuple[list[User], int]:
        return self._repo.list(skip, limit, status_ativo)

    def update(self, user_id: str, payload: UserUpdate) -> User:
        user = self.get(user_id)
        if payload.email != user.email and self._repo.get_by_email(payload.email):
            raise _conflict("E-mail já cadastrado", "EMAIL_ALREADY_EXISTS")
        user.email = payload.email
        user.telefone = payload.telefone
        user.idade = payload.idade
        if payload.termos_contrato is not None:
            user.termos_contrato = payload.termos_contrato
        try:
            self._repo.commit()
        except IntegrityError:
            self._repo.rollback()
            raise _conflict("E-mail já cadastrado", "EMAIL_ALREADY_EXISTS") from None
        return user

    def set_status(self, user_id: str, status_ativo: bool) -> User:
        user = self.get(user_id)
        user.status_ativo = status_ativo
        self._repo.commit()
        return user

    def set_admin(self, user_id: str, interno_adm: bool) -> User:
        user = self.get(user_id)
        user.interno_adm = interno_adm
        self._repo.commit()
        return user
