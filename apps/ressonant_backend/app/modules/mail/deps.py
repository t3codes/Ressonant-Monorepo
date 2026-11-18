from typing import Annotated

from app.database.engine import get_db
from app.modules.mail.dataproviders.repository import MailRepository
from app.modules.mail.usecases.services import MailService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_mail_repository(db: Annotated[Session, Depends(get_db)]) -> MailRepository:
    return MailRepository(db)


def get_mail_service(
    repo: Annotated[MailRepository, Depends(get_mail_repository)],
) -> MailService:
    return MailService(repo)
