from typing import Annotated

from app.database.engine import get_db
from app.modules.billing.dataproviders.repository import BillingRepository
from app.modules.billing.dataproviders.stub_gateway import StubBillingGateway
from app.modules.billing.domain.gateway import BillingGateway
from app.modules.billing.usecases.services import BillingService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_billing_repository(db: Annotated[Session, Depends(get_db)]) -> BillingRepository:
    return BillingRepository(db)


def get_billing_gateway() -> BillingGateway:
    return StubBillingGateway()


def get_billing_service(
    repo: Annotated[BillingRepository, Depends(get_billing_repository)],
    gateway: Annotated[BillingGateway, Depends(get_billing_gateway)],
) -> BillingService:
    return BillingService(repo, gateway)
