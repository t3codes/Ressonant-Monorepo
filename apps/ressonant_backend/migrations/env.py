from alembic import context
from app.config.settings import get_settings
from app.database.engine import Base
from app.modules.billing.domain.models import Plan, Subscription  # noqa: F401
from app.modules.chat.domain.models import (  # noqa: F401
    Channel,
    Conversation,
    Message,
)
from app.modules.kanban_boards.domain.models import Board, BoardColumn  # noqa: F401
from app.modules.kanban_cards.domain.models import (  # noqa: F401
    Card,
    CardChecklist,
    CardComment,
    CardCustomField,
    CardHistory,
    CardLink,
    CardSubtask,
    CardWatcher,
    CardWorklog,
)
from app.modules.mail.domain.models import Email  # noqa: F401
from app.modules.notifications.domain.models import AppNotification  # noqa: F401
from app.modules.organization.domain.models import (  # noqa: F401
    Invitation,
    Organization,
    OrganizationMember,
)
from app.modules.reactions.domain.models import MessageReaction  # noqa: F401
from app.modules.readstates.domain.models import ReadState  # noqa: F401
from app.modules.teams.domain.models import Team, TeamMember  # noqa: F401
from app.modules.workspace.domain.models import Workspace, WorkspaceMember  # noqa: F401
from app.modules.workspace_management.domain.models import (  # noqa: F401
    AuditEvent,
    WorkspaceManagementGrant,
)
from app.user import models  # noqa: F401
from sqlalchemy import create_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
