import json

from app.modules.mail.dataproviders.repository import MailRepository
from app.modules.mail.domain.models import Email
from app.modules.mail.schemas.dto import EmailCreate, EmailList, EmailResponse, MailUserChange
from common.errors import ExceptionData, NotFoundException


class MailService:
    def __init__(self, repository: MailRepository) -> None:
        self._repo = repository

    def list_for_user(self, user_id: str, skip: int = 0, limit: int = 50) -> EmailList:
        items, total = self._repo.list_for_user(user_id, skip, limit)
        return EmailList(
            items=[EmailResponse.model_validate(i) for i in items],
            total=total,
            skip=skip,
            limit=limit,
        )

    def get_by_id(self, email_id: str) -> Email | None:
        return self._repo.get_by_id(email_id)

    def create(self, payload: EmailCreate) -> Email:
        email = Email(
            workspace_id="",  # Será preenchido pelo contexto do workspace
            sender_id=payload.sender_id,
            recipient_ids=json.dumps(payload.recipient_ids),
            cc_ids=json.dumps(payload.cc_ids or []),
            bcc_ids=json.dumps(payload.bcc_ids or []),
            subject=payload.subject,
            body=payload.body,
            thread_id=payload.thread_id,
            is_reply=payload.is_reply,
            forwarded=payload.forwarded,
            attachments=json.dumps(payload.attachments or []),
        )
        try:
            self._repo.add(email)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return email

    def mark_read(self, email_id: str, user_id: str) -> Email:
        email = self.get_by_id(email_id)
        if email is None:
            raise NotFoundException(
                ExceptionData(message="E-mail não encontrado", error_code="EMAIL_NOT_FOUND"),
                is_expected=True,
            )
        return email

    def update_for_user(self, email_id: str, user_id: str, change: MailUserChange) -> Email:
        email = self.get_by_id(email_id)
        if email is None:
            raise NotFoundException(
                ExceptionData(message="E-mail não encontrado", error_code="EMAIL_NOT_FOUND"),
                is_expected=True,
            )
        # Aplicar mudanças de lixeira/favorito/lembrete
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return email
