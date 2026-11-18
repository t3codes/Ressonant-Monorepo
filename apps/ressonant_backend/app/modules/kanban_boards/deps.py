from typing import Annotated

from app.database.engine import get_db
from app.modules.kanban_boards.dataproviders.repository import (
    BoardColumnRepository,
    BoardRepository,
)
from app.modules.kanban_boards.usecases.services import BoardService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_board_repository(db: Annotated[Session, Depends(get_db)]) -> BoardRepository:
    return BoardRepository(db)


def get_column_repository(db: Annotated[Session, Depends(get_db)]) -> BoardColumnRepository:
    return BoardColumnRepository(db)


def get_board_service(
    repo: Annotated[BoardRepository, Depends(get_board_repository)],
    col_repo: Annotated[BoardColumnRepository, Depends(get_column_repository)],
) -> BoardService:
    return BoardService(repo, col_repo)
