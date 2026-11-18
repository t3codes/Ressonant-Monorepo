"""Compatibilidade: re-exporta do novo layout modular."""
from app.modules.kanban_cards.dataproviders.repository import CardRepository  # noqa: F401
from app.modules.kanban_cards.deps import get_card_service, get_card_repository, get_board_repository  # noqa: F401
from app.modules.kanban_cards.domain.models import Card  # noqa: F401
from app.modules.kanban_cards.entrypoints.routes import router  # noqa: F401
from app.modules.kanban_cards.schemas.dto import (  # noqa: F401
    CardCreate,
    CardList,
    CardMoveInput,
    CardResponse,
    CardUpdate,
)
from app.modules.kanban_cards.usecases.services import CardService  # noqa: F401
