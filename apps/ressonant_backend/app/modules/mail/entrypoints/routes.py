from typing import Annotated

from app.modules.auth.deps import CurrentUser
from app.modules.mail.deps import get_mail_service
from app.modules.mail.schemas.dto import EmailCreate, EmailList, EmailResponse, MailUserChange
from app.modules.mail.usecases.services import MailService
from fastapi import APIRouter, Depends, Query, status

router = APIRouter(prefix="/mail", tags=["mail"])

Service = Annotated[MailService, Depends(get_mail_service)]


@router.post("", response_model=EmailResponse, status_code=status.HTTP_201_CREATED)
def create_email(
    payload: EmailCreate,
    user: CurrentUser,
    service: Service,
) -> EmailResponse:
    return EmailResponse.model_validate(service.create(payload))


@router.get("", response_model=EmailList)
def list_emails(
    user: CurrentUser,
    service: Service,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EmailList:
    return service.list_for_user(user.id, skip, limit)


@router.get("/{email_id}", response_model=EmailResponse)
def get_email(
    email_id: str,
    user: CurrentUser,
    service: Service,
) -> EmailResponse:
    email = service.get_by_id(email_id)
    if email is None:
        from common.errors import ExceptionData, NotFoundException

        raise NotFoundException(
            ExceptionData(message="E-mail não encontrado", error_code="EMAIL_NOT_FOUND"),
            is_expected=True,
        )
    return EmailResponse.model_validate(email)


@router.patch("/{email_id}/read", response_model=EmailResponse)
def mark_email_read(
    email_id: str,
    user: CurrentUser,
    service: Service,
) -> EmailResponse:
    return service.mark_read(email_id, user.id)


@router.patch("/{email_id}", response_model=EmailResponse)
def update_email_for_user(
    email_id: str,
    change: MailUserChange,
    user: CurrentUser,
    service: Service,
) -> EmailResponse:
    return service.update_for_user(email_id, user.id, change)
