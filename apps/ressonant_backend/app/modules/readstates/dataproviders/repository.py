from app.modules.readstates.domain.models import ReadState
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class ReadStateRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_user(self, user_id: str) -> list[ReadState]:
        return self._db.scalars(select(ReadState).where(ReadState.user_id == user_id)).all()

    def mark_read(self, user_id: str, room_id: str) -> ReadState:
        existing = self._db.scalar(
            select(ReadState).where(
                ReadState.user_id == user_id,
                ReadState.room_id == room_id,
            )
        )
        if existing:
            existing.last_read_at = func.now()
            self._db.flush()
            return existing
        read_state = ReadState(user_id=user_id, room_id=room_id)
        self._db.add(read_state)
        self._db.flush()
        return read_state

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
