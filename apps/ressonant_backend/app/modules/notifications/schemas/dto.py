from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class NotificationCreate(BaseModel):
    user_id: str
    kind: Annotated[str, Field(min_length=1, max_length=50)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    body: str | None = None


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    kind: str
    title: str
    body: str | None
    read_at: datetime | None
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationResponse]
    total: int
    skip: int
    limit: int
