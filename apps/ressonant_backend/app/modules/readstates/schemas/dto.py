from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReadStateCreate(BaseModel):
    user_id: str
    room_id: str


class ReadStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    room_id: str
    last_read_at: datetime


class ReadStateList(BaseModel):
    items: list[ReadStateResponse]
    total: int
