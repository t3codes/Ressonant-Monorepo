"""Compatibilidade: re-exporta do novo layout modular."""
from app.modules.kanban_boards.dataproviders.repository import BoardColumnRepository, BoardRepository  # noqa: F401
from app.modules.kanban_boards.deps import get_board_service, get_board_repository, get_column_repository  # noqa: F401
from app.modules.kanban_boards.domain.models import Board, BoardColumn  # noqa: F401
from app.modules.kanban_boards.entrypoints.routes import router  # noqa: F401
from app.modules.kanban_boards.schemas.dto import (  # noqa: F401
    BoardColumnCreate,
    BoardColumnList,
    BoardColumnResponse,
    BoardCreate,
    BoardList,
    BoardResponse,
    BoardStatusUpdate,
    BoardUpdate,
)
from app.modules.kanban_boards.usecases.services import BoardService  # noqa: F401
