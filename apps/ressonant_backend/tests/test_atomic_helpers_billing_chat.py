"""Helpers add-only de canal e trial: gravam na Session, quem chama comita."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.common.exceptions import ConflictException
from app.modules.billing.dataproviders.repository import BillingRepository
from app.modules.billing.dataproviders.stub_gateway import StubBillingGateway
from app.modules.billing.domain.models import Plan, Subscription
from app.modules.billing.schemas.dto import BillingResponse
from app.modules.billing.usecases.services import BillingService
from app.modules.chat.dataproviders.repository import ChannelRepository
from app.modules.chat.domain.models import Channel
from app.modules.chat.schemas.dto import ChannelCreate
from app.modules.chat.usecases.services import ChannelService
from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.user.domain.models import User
from app.modules.workspace_management.domain.models import AuditEvent
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import VALID_CPFS, make_user

TRIAL_DAYS = 7


def _count_in(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def _count(session_factory: sessionmaker[Session], model: type) -> int:
    with session_factory() as db:
        return _count_in(db, model)


def _channel_payload() -> ChannelCreate:
    return ChannelCreate(
        workspace_id=str(uuid.uuid4()), name="Canal Geral", topic="Abertura", visibility="public"
    )


def _seed_plan(
    session_factory: sessionmaker[Session],
    *,
    code: str = "inicial",
    seat_limit: int | None = 3,
) -> None:
    with session_factory() as db:
        db.add(
            Plan(
                id=str(uuid.uuid4()),
                code=code,
                name="Inicial",
                price_cents=0,
                currency="BRL",
                seat_limit=seat_limit,
                overage_cents_per_seat=None,
                trial_days=TRIAL_DAYS,
                active=True,
            )
        )
        db.commit()


def _seed_owner(
    session_factory: sessionmaker[Session], *, email: str, cpf: str
) -> tuple[User, str]:
    owner = make_user(session_factory, email=email, cpf=cpf)
    organization_id = str(uuid.uuid4())
    with session_factory() as db:
        db.add(Organization(id=organization_id, name="Org Billing", slug=f"org-{uuid.uuid4()}"))
        db.add(
            OrganizationMember(
                organization_id=organization_id,
                user_id=owner.id,
                role="owner",
                status="active",
            )
        )
        db.commit()
    return owner, organization_id


def _add_member(
    session_factory: sessionmaker[Session], organization_id: str, *, email: str, cpf: str
) -> None:
    member = make_user(session_factory, email=email, cpf=cpf)
    with session_factory() as db:
        db.add(
            OrganizationMember(
                organization_id=organization_id,
                user_id=member.id,
                role="member",
                status="active",
            )
        )
        db.commit()


def test_add_channel_stages_without_commit(session_factory: sessionmaker[Session]) -> None:
    created_by = str(uuid.uuid4())
    payload = _channel_payload()

    with session_factory() as db:
        channel = ChannelService(ChannelRepository(db)).add_channel(payload, created_by)
        assert channel.id
        assert channel.slug == "canal-geral"
        assert channel.workspace_id == payload.workspace_id
        assert json.loads(channel.member_ids) == [created_by]
        assert channel.created_by == created_by
        assert db.in_transaction()
        assert _count_in(db, Channel) == 1

    assert _count(session_factory, Channel) == 0

    with session_factory() as db:
        staged = ChannelService(ChannelRepository(db)).add_channel(payload, created_by)
        db.commit()
        assert staged.id

    assert _count(session_factory, Channel) == 1


def test_add_channel_explicit_slug_and_create_default_slug(
    session_factory: sessionmaker[Session],
) -> None:
    created_by = str(uuid.uuid4())

    with session_factory() as db:
        service = ChannelService(ChannelRepository(db))
        explicit = service.add_channel(_channel_payload(), created_by, slug="geral-custom")
        assert explicit.slug == "geral-custom"
        assert explicit.name == "Canal Geral"
        db.commit()

        default = service.create(_channel_payload(), created_by)
        assert default.slug == "canal-geral"
        assert default.name == "Canal Geral"

    assert _count(session_factory, Channel) == 2


def test_channel_create_commits(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as db:
        channel = ChannelService(ChannelRepository(db)).create(
            _channel_payload(), str(uuid.uuid4())
        )
        assert channel.id

    assert _count(session_factory, Channel) == 1


def test_add_trial_subscription_stages_without_commit(
    session_factory: sessionmaker[Session],
) -> None:
    owner, organization_id = _seed_owner(
        session_factory, email="ana@example.com", cpf=VALID_CPFS[0]
    )
    _seed_plan(session_factory)

    with session_factory() as db:
        service = BillingService(BillingRepository(db), StubBillingGateway())
        before = datetime.now(UTC)
        subscription = service.add_trial_subscription(organization_id, owner, seats_purchased=2)
        after = datetime.now(UTC)
        assert subscription.id
        assert subscription.status == "trialing"
        assert subscription.seats_purchased == 2
        assert subscription.gateway_ref.startswith("stub_")
        assert before + timedelta(days=TRIAL_DAYS) <= subscription.trial_ends_at
        assert subscription.trial_ends_at <= after + timedelta(days=TRIAL_DAYS)
        assert db.in_transaction()
        assert _count_in(db, Subscription) == 1
        assert _count_in(db, AuditEvent) == 1
        event = db.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "billing.subscription.created",
                AuditEvent.organization_id == organization_id,
            )
        )
        assert event is not None
        assert event.actor_user_id == owner.id
        assert event.actor_role == "owner"
        assert event.entity_id == subscription.id
        assert event.after["plan_code"] == "inicial"

    assert _count(session_factory, Subscription) == 0
    assert _count(session_factory, AuditEvent) == 0

    with session_factory() as db:
        service = BillingService(BillingRepository(db), StubBillingGateway())
        service.add_trial_subscription(organization_id, owner)
        db.commit()

    assert _count(session_factory, Subscription) == 1
    assert _count(session_factory, AuditEvent) == 1


def test_create_subscription_commits_and_returns_response(
    session_factory: sessionmaker[Session],
) -> None:
    owner, organization_id = _seed_owner(
        session_factory, email="bia@example.com", cpf=VALID_CPFS[0]
    )
    _seed_plan(session_factory)

    with session_factory() as db:
        response = BillingService(BillingRepository(db), StubBillingGateway()).create_subscription(
            organization_id, owner, request_id="req-atomica-1"
        )
        assert isinstance(response, BillingResponse)
        assert response.organization_id == organization_id
        assert response.provider == "stub"
        assert response.simulation is True
        assert response.subscription is not None
        assert response.subscription.status == "trialing"
        assert response.subscription.gateway_ref.startswith("stub_")

    assert _count(session_factory, Subscription) == 1
    assert _count(session_factory, AuditEvent) == 1


def test_add_trial_subscription_reads_flushed_owner_in_same_session(
    session_factory: sessionmaker[Session],
) -> None:
    """B2.4: papel vem do banco via flush, sem commit prévio da organização."""
    actor = make_user(session_factory, email="caio@example.com", cpf=VALID_CPFS[0])
    _seed_plan(session_factory)

    with session_factory() as db:
        organization = Organization(name="Org Nova", slug=f"org-{uuid.uuid4()}")
        db.add(organization)
        db.flush()
        db.add(
            OrganizationMember(
                organization_id=organization.id,
                user_id=actor.id,
                role="owner",
                status="active",
            )
        )
        db.flush()

        subscription = BillingService(
            BillingRepository(db), StubBillingGateway()
        ).add_trial_subscription(organization.id, actor)
        assert subscription.status == "trialing"
        assert _count_in(db, Subscription) == 1
        assert _count_in(db, AuditEvent) == 1
        db.commit()

    assert _count(session_factory, Subscription) == 1
    assert _count(session_factory, AuditEvent) == 1


def test_add_trial_subscription_duplicate_active_keeps_error_code(
    session_factory: sessionmaker[Session],
) -> None:
    owner, organization_id = _seed_owner(
        session_factory, email="dia@example.com", cpf=VALID_CPFS[0]
    )
    _seed_plan(session_factory)

    with session_factory() as db:
        service = BillingService(BillingRepository(db), StubBillingGateway())
        service.add_trial_subscription(organization_id, owner)
        db.commit()

        with pytest.raises(ConflictException) as duplicated:
            service.add_trial_subscription(organization_id, owner)
        assert duplicated.value.exception_data.error_code == "SUBSCRIPTION_ALREADY_ACTIVE"
        assert str(duplicated.value) == "A organização já possui uma assinatura ativa."

    assert _count(session_factory, Subscription) == 1
    assert _count(session_factory, AuditEvent) == 1


def test_add_trial_subscription_seat_limit_keeps_error_code(
    session_factory: sessionmaker[Session],
) -> None:
    owner, organization_id = _seed_owner(
        session_factory, email="elo@example.com", cpf=VALID_CPFS[0]
    )
    _add_member(session_factory, organization_id, email="fabio@example.com", cpf=VALID_CPFS[1])
    _seed_plan(session_factory, seat_limit=1)

    with session_factory() as db:
        with pytest.raises(ConflictException) as exceeded:
            BillingService(BillingRepository(db), StubBillingGateway()).add_trial_subscription(
                organization_id, owner
            )
        assert exceeded.value.exception_data.error_code == "SEAT_LIMIT_EXCEEDED"
        assert _count_in(db, Subscription) == 0
        assert _count_in(db, AuditEvent) == 0

    assert _count(session_factory, Subscription) == 0
    assert _count(session_factory, AuditEvent) == 0


def test_create_subscription_rollback_leaves_no_orphans(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, organization_id = _seed_owner(
        session_factory, email="gabi@example.com", cpf=VALID_CPFS[0]
    )
    _seed_plan(session_factory)

    def fail_audit(repository: BillingRepository, event: AuditEvent) -> AuditEvent:
        raise RuntimeError("falha ao gravar auditoria")

    monkeypatch.setattr(BillingRepository, "add_audit_event", fail_audit)
    with session_factory() as db:
        with pytest.raises(RuntimeError, match="falha ao gravar auditoria"):
            BillingService(BillingRepository(db), StubBillingGateway()).create_subscription(
                organization_id, owner
            )
        assert _count_in(db, Subscription) == 0
        assert _count_in(db, AuditEvent) == 0

    assert _count(session_factory, Subscription) == 0
    assert _count(session_factory, AuditEvent) == 0
