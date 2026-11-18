"""Compatibilidade: re-exporta do novo layout modular."""
from app.modules.reactions.dataproviders.repository import ReactionRepository  # noqa: F401
from app.modules.reactions.deps import get_reaction_service, get_reaction_repository  # noqa: F401
from app.modules.reactions.domain.models import MessageReaction  # noqa: F401
from app.modules.reactions.entrypoints.routes import router  # noqa: F401
from app.modules.reactions.schemas.dto import ReactionList, ReactionResponse, ReactionToggle  # noqa: F401
from app.modules.reactions.usecases.services import ReactionService  # noqa: F401
