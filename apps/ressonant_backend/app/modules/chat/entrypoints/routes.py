from typing import Annotated

from app.modules.auth.deps import CurrentUser
from app.modules.chat.deps import (
    get_channel_service,
    get_conversation_service,
    get_message_service,
)
from app.modules.chat.schemas.dto import (
    ChannelCreate,
    ChannelList,
    ChannelResponse,
    ConversationCreate,
    ConversationList,
    ConversationResponse,
    MessageCreate,
    MessageList,
    MessageResponse,
    MessageUpdate,
)
from app.modules.chat.usecases.services import ChannelService, ConversationService, MessageService
from fastapi import APIRouter, Depends, Query, status

router = APIRouter(prefix="/channels", tags=["channels"])

ChannelServiceDep = Annotated[ChannelService, Depends(get_channel_service)]
ConversationServiceDep = Annotated[ConversationService, Depends(get_conversation_service)]
MessageServiceDep = Annotated[MessageService, Depends(get_message_service)]


@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
def create_channel(
    payload: ChannelCreate,
    user: CurrentUser,
    service: ChannelServiceDep,
) -> ChannelResponse:
    return ChannelResponse.model_validate(service.create(payload))


@router.get("", response_model=ChannelList)
def list_channels(
    workspace_id: str,
    service: ChannelServiceDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ChannelList:
    items, total = service.list_by_workspace(workspace_id, skip, limit)
    return ChannelList(
        items=[ChannelResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{channel_id}", response_model=ChannelResponse)
def get_channel(
    channel_id: str,
    service: ChannelServiceDep,
) -> ChannelResponse:
    channel = service.get_by_id(channel_id)
    if channel is None:
        from common.errors import ExceptionData, NotFoundException

        raise NotFoundException(
            ExceptionData(message="Canal não encontrado", error_code="CHANNEL_NOT_FOUND"),
            is_expected=True,
        )
    return ChannelResponse.model_validate(channel)


@router.post(
    "/{channel_id}/members", response_model=ChannelResponse, status_code=status.HTTP_200_OK
)
def add_channel_member(
    channel_id: str,
    user_id: str,
    user: CurrentUser,
    service: ChannelServiceDep,
) -> ChannelResponse:
    return ChannelResponse.model_validate(service.add_member(channel_id, user_id))


conversation_router = APIRouter(prefix="/conversations", tags=["conversations"])


@conversation_router.post(
    "", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED
)
def create_conversation(
    payload: ConversationCreate,
    service: ConversationServiceDep,
) -> ConversationResponse:
    return ConversationResponse.model_validate(service.create(payload))


@conversation_router.get("", response_model=ConversationList)
def list_conversations(
    workspace_id: str,
    service: ConversationServiceDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ConversationList:
    items, total = service.list_by_workspace(workspace_id, skip, limit)
    return ConversationList(
        items=[ConversationResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@conversation_router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: str,
    service: ConversationServiceDep,
) -> ConversationResponse:
    conversation = service.get_by_id(conversation_id)
    if conversation is None:
        from common.errors import ExceptionData, NotFoundException

        raise NotFoundException(
            ExceptionData(message="Conversa não encontrada", error_code="CONVERSATION_NOT_FOUND"),
            is_expected=True,
        )
    return ConversationResponse.model_validate(conversation)


message_router = APIRouter(prefix="/messages", tags=["messages"])


@message_router.post("", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def create_message(
    payload: MessageCreate,
    user: CurrentUser,
    service: MessageServiceDep,
) -> MessageResponse:
    return MessageResponse.model_validate(service.create(payload))


@message_router.get("", response_model=MessageList)
def list_messages(
    room_id: str,
    service: MessageServiceDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MessageList:
    items, total = service.list_by_room(room_id, skip, limit)
    return MessageList(
        items=[MessageResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@message_router.get("/{message_id}", response_model=MessageResponse)
def get_message(
    message_id: str,
    service: MessageServiceDep,
) -> MessageResponse:
    message = service.get_by_id(message_id)
    if message is None:
        from common.errors import ExceptionData, NotFoundException

        raise NotFoundException(
            ExceptionData(message="Mensagem não encontrada", error_code="MESSAGE_NOT_FOUND"),
            is_expected=True,
        )
    return MessageResponse.model_validate(message)


@message_router.put("/{message_id}", response_model=MessageResponse)
def update_message(
    message_id: str,
    payload: MessageUpdate,
    user: CurrentUser,
    service: MessageServiceDep,
) -> MessageResponse:
    return MessageResponse.model_validate(service.update(message_id, payload, user.id))


@message_router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(
    message_id: str,
    user: CurrentUser,
    service: MessageServiceDep,
) -> None:
    service.soft_delete(message_id, user.id)
    return None
