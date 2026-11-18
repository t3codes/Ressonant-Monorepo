from typing import Annotated

from app.database.engine import get_db
from app.modules.kanban_boards.dataproviders.repository import BoardRepository
from app.modules.kanban_cards.dataproviders.repository import CardRepository
from app.modules.kanban_cards.usecases.services import CardService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_card_repository(db: Annotated[Session, Depends(get_db)]) -> CardRepository:
    return CardRepository(db)


def get_board_repository(db: Annotated[Session, Depends(get_db)]) -> BoardRepository:
    return BoardRepository(db)


def get_card_service(
    card_repo: Annotated[CardRepository, Depends(get_card_repository)],
    board_repo: Annotated[BoardRepository, Depends(get_board_repository)],
) -> CardService:
    return CardService(card_repo, board_repo)
