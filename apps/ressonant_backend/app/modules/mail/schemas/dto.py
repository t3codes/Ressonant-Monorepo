from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class EmailBase(BaseModel):
    sender_id: str
    recipient_ids: list[str]
    cc_ids: list[str] | None = None
    bcc_ids: list[str] | None = None
    attachments: list[dict] | None = None
    subject: Annotated[str, Field(min_length=1, max_length=300)]
    body: Annotated[str, Field(min_length=1)]
    thread_id: str | None = None
    is_reply: bool = False
    forwarded: bool = False


class EmailCreate(EmailBase):
    pass


class EmailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    sender_id: str
    recipient_ids: str
    cc_ids: str | None
    bcc_ids: str | None
    subject: str
    body: str
    thread_id: str | None
    is_reply: bool
    forwarded: bool
    attachments: str | None
    status_ativo: bool
    criado_em: datetime
    atualizado_em: datetime


class EmailList(BaseModel):
    items: list[EmailResponse]
    total: int
    skip: int
    limit: int


class MailUserChange(BaseModel):
    trashed: bool | None = None
    starred: bool | None = None
    remindAt: str | None = None
