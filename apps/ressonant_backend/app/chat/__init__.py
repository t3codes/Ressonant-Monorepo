"""Compatibilidade: re-exporta do novo layout modular."""
from app.modules.chat.dataproviders.repository import ChannelRepository, ConversationRepository, MessageRepository  # noqa: F401
from app.modules.chat.deps import (  # noqa: F401
    get_channel_service,
    get_channel_repository,
    get_conversation_service,
    get_conversation_repository,
    get_message_service,
    get_message_repository,
)
from app.modules.chat.domain.models import Channel, Conversation, Message  # noqa: F401
from app.modules.chat.entrypoints.routes import router, conversation_router, message_router  # noqa: F401
from app.modules.chat.schemas.dto import (  # noqa: F401
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
from app.modules.chat.usecases.services import ChannelService, ConversationService, MessageService  # noqa: F401
