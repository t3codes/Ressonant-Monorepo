import uuid

import pytest
from app.config.settings import get_settings
from app.modules.workspace.domain.models import Workspace
from app.modules.workspace_management.dataproviders.repository import WorkspaceManagementRepository
from app.modules.workspace_management.domain.models import AuditEvent
from app.modules.workspace_management.usecases.services import WorkspaceManagementService
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from tests.conftest import VALID_CPFS, make_user


def test_card_scoped_audit_event_roundtrip(session_factory) -> None:
    owner = make_user(session_factory, email="audit-owner@r.dev", cpf=VALID_CPFS[0])
    with session_factory() as db:
        workspace = Workspace(name="Audit", slug="ws-audit-card", owner_id=owner.id)
        db.add(workspace)
        db.flush()
        organization_id = workspace.organization_id
        assert organization_id is not None

        repo = WorkspaceManagementRepository(db)
        repo.add_audit_event(
            AuditEvent(
                workspace_id=workspace.id,
                organization_id=organization_id,
                scope="card",
                actor_user_id=owner.id,
                actor_type="user",
                actor_role="tech_lead",
                permission_version=3,
                action="card.blocked",
                entity_type="card",
                entity_id=str(uuid.uuid4()),
                request_id="req-card-audit",
                result="success",
            )
        )
        # Existing callers still get the historical default scope.
        repo.add_audit_event(
            AuditEvent(
                workspace_id=workspace.id,
                actor_type="system",
                action="system.check",
                entity_type="system",
                entity_id="check-1",
            )
        )
        repo.commit()

    with session_factory() as db:
        repo = WorkspaceManagementRepository(db)
        events = {e.action: e for e in repo.list_audit_events(workspace.id)}

    card_event = events["card.blocked"]
    assert card_event.scope == "card"
    assert card_event.organization_id == organization_id
    assert card_event.actor_role == "tech_lead"
    assert card_event.permission_version == 3
    assert card_event.request_id == "req-card-audit"
    assert events["system.check"].scope == "workspace"


def test_audit_derives_actor_role_from_actor_type() -> None:
    class CapturingRepository:
        def __init__(self) -> None:
            self.events: list[AuditEvent] = []

        def add_audit_event(self, event: AuditEvent) -> AuditEvent:
            self.events.append(event)
            return event

    repo = CapturingRepository()
    WorkspaceManagementService(repo)._audit(  # type: ignore[arg-type]
        actor=None,
        action="system.check",
        entity_type="system",
        entity_id="check-1",
    )
    event = repo.events[0]
    assert event.actor_role == "system"
    assert event.scope == "workspace"


def test_redact_removes_sensitive_audit_fields() -> None:
    payload = {
        "senha": "hunter2",
        "password": "hunter2",
        "token": "abc",
        "secret": "abc",
        "cpf": "52998224725",
        "telefone": "11987654321",
        "email": "ana@ressonant.dev",
        "authorization": "Bearer abc",
        "level": "modify",
    }
    redacted = WorkspaceManagementService._redact(payload)
    assert redacted is not None
    sensitive = (
        "senha",
        "password",
        "token",
        "secret",
        "cpf",
        "telefone",
        "email",
        "authorization",
    )
    for key in sensitive:
        assert redacted[key] == "[REDACTED]"
    assert redacted["level"] == "modify"


@pytest.mark.skipif(
    not get_settings().database_url.lower().startswith("postgresql"),
    reason="append-only privileges and trigger are PostgreSQL-only",
)
def test_postgres_rejects_direct_update_and_delete_on_audit_events() -> None:
    engine = create_engine(get_settings().database_url)
    insert = text(
        "INSERT INTO audit_events (id, actor_type, action, entity_type, entity_id, scope) "
        "VALUES (:id, 'system', 'test.append_only', 'test', :id, 'workspace')"
    )
    try:
        for statement in (
            text("UPDATE audit_events SET action = 'x' WHERE id = :id"),
            text("DELETE FROM audit_events WHERE id = :id"),
        ):
            with engine.connect() as connection:
                transaction = connection.begin()
                event_id = str(uuid.uuid4())
                connection.execute(insert, {"id": event_id})
                with pytest.raises(SQLAlchemyError):
                    connection.execute(statement, {"id": event_id})
                transaction.rollback()
    finally:
        engine.dispose()
