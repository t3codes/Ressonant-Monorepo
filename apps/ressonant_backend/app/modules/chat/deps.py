from typing import Annotated

from app.database.engine import get_db
from app.modules.chat.dataproviders.repository import (
    ChannelRepository,
    ConversationRepository,
    MessageRepository,
)
from app.modules.chat.usecases.chat_realtime_usecase import (
    ChatRealtimeService,
    build_chat_realtime_usecase,
)
from app.modules.chat.usecases.services import ChannelService, ConversationService, MessageService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_channel_repository(db: Annotated[Session, Depends(get_db)]) -> ChannelRepository:
    return ChannelRepository(db)


def get_channel_service(
    repo: Annotated[ChannelRepository, Depends(get_channel_repository)],
) -> ChannelService:
    return ChannelService(repo)


def get_conversation_repository(db: Annotated[Session, Depends(get_db)]) -> ConversationRepository:
    return ConversationRepository(db)


def get_conversation_service(
    repo: Annotated[ConversationRepository, Depends(get_conversation_repository)],
) -> ConversationService:
    return ConversationService(repo)


def get_message_repository(db: Annotated[Session, Depends(get_db)]) -> MessageRepository:
    return MessageRepository(db)


def get_message_service(
    repo: Annotated[MessageRepository, Depends(get_message_repository)],
) -> MessageService:
    return MessageService(repo)


def get_chat_realtime_service(
    db: Annotated[Session, Depends(get_db)],
) -> ChatRealtimeService:
    return build_chat_realtime_usecase(db)
