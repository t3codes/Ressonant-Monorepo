from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ReactionToggle(BaseModel):
    message_id: str
    user_id: str
    emoji: Annotated[str, Field(min_length=1, max_length=10)]


class ReactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    message_id: str
    user_id: str
    emoji: str
    criado_em: datetime


class ReactionList(BaseModel):
    items: list[ReactionResponse]
    total: int
