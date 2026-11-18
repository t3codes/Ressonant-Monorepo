"""Compatibilidade: re-exporta do novo layout modular."""
from app.modules.readstates.dataproviders.repository import ReadStateRepository  # noqa: F401
from app.modules.readstates.deps import get_read_state_service, get_read_state_repository  # noqa: F401
from app.modules.readstates.domain.models import ReadState  # noqa: F401
from app.modules.readstates.entrypoints.routes import router  # noqa: F401
from app.modules.readstates.schemas.dto import ReadStateCreate, ReadStateList, ReadStateResponse  # noqa: F401
from app.modules.readstates.usecases.services import ReadStateService  # noqa: F401
