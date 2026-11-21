import socket
import uuid
from unittest.mock import patch

import pytest
from app.modules.billing.dataproviders.stub_gateway import StubBillingGateway
from app.modules.billing.domain.gateway import BillingGateway
from app.modules.billing.domain.models import SUBSCRIPTION_STATUSES, Plan, Subscription
from app.modules.organization.domain.models import Organization
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker


def test_stub_gateway_is_a_billing_gateway() -> None:
    assert isinstance(StubBillingGateway(), BillingGateway)


def test_stub_gateway_makes_no_network_call() -> None:
    gateway = StubBillingGateway()

    with patch.object(socket, "socket", side_effect=AssertionError("rede nao permitida")):
        intent = gateway.create_subscription_intent(
            organization_id=str(uuid.uuid4()), plan_code="equipe", seats_purchased=0
        )

    assert intent.confirmed is True
    assert intent.gateway_ref.startswith("stub_")


@pytest.mark.parametrize("status", SUBSCRIPTION_STATUSES)
def test_subscription_accepts_all_domain_statuses(status: str) -> None:
    subscription = Subscription(
        organization_id=str(uuid.uuid4()),
        plan_id=str(uuid.uuid4()),
        status=status,
        seats_purchased=0,
    )

    assert subscription.status == status


def test_only_one_active_subscription_per_organization(
    session_factory: sessionmaker[Session],
) -> None:
    organization_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    with session_factory() as db:
        db.add(Organization(id=organization_id, name="Acme", slug="acme"))
        db.add(
            Plan(
                id=plan_id,
                code="equipe",
                name="Equipe",
                price_cents=4900,
                currency="BRL",
                seat_limit=15,
                overage_cents_per_seat=4900,
                trial_days=14,
                active=True,
            )
        )
        db.add(
            Subscription(
                organization_id=organization_id,
                plan_id=plan_id,
                status="trialing",
                seats_purchased=0,
            )
        )
        db.commit()

        db.add(
            Subscription(
                organization_id=organization_id,
                plan_id=plan_id,
                status="active",
                seats_purchased=0,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
