"""Compatibilidade: re-exporta do novo layout modular."""
from app.modules.notifications.dataproviders.repository import NotificationRepository  # noqa: F401
from app.modules.notifications.deps import get_notification_service, get_notification_repository  # noqa: F401
from app.modules.notifications.domain.models import AppNotification  # noqa: F401
from app.modules.notifications.entrypoints.routes import router  # noqa: F401
from app.modules.notifications.schemas.dto import NotificationCreate, NotificationList, NotificationResponse  # noqa: F401
from app.modules.notifications.usecases.services import NotificationService  # noqa: F401
