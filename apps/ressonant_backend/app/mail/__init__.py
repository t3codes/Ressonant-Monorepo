"""Compatibilidade: re-exporta do novo layout modular."""
from app.modules.mail.dataproviders.repository import MailRepository  # noqa: F401
from app.modules.mail.deps import get_mail_service, get_mail_repository  # noqa: F401
from app.modules.mail.domain.models import Email  # noqa: F401
from app.modules.mail.entrypoints.routes import router  # noqa: F401
from app.modules.mail.schemas.dto import EmailCreate, EmailList, EmailResponse, MailUserChange  # noqa: F401
from app.modules.mail.usecases.services import MailService  # noqa: F401
