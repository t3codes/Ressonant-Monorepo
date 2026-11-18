from app.modules.readstates.dataproviders.repository import ReadStateRepository
from app.modules.readstates.schemas.dto import ReadStateList, ReadStateResponse


class ReadStateService:
    def __init__(self, repository: ReadStateRepository) -> None:
        self._repo = repository

    def list_for_user(self, user_id: str) -> ReadStateList:
        states = self._repo.list_for_user(user_id)
        return ReadStateList(
            items=[ReadStateResponse.model_validate(s) for s in states],
            total=len(states),
        )

    def mark_read(self, user_id: str, room_id: str) -> ReadStateResponse:
        state = self._repo.mark_read(user_id, room_id)
        self._repo.commit()
        return ReadStateResponse.model_validate(state)
