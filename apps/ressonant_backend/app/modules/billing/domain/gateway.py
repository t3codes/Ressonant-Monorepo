from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SubscriptionIntent:
    """Resultado da intenção de assinatura; nenhum valor aqui é cobrado."""

    gateway_ref: str
    confirmed: bool


@runtime_checkable
class BillingGateway(Protocol):
    """Porta de intenção de assinatura, sem conhecer provider ou credenciais."""

    def create_subscription_intent(
        self, *, organization_id: str, plan_code: str, seats_purchased: int
    ) -> SubscriptionIntent:
        """Confirma a intenção e devolve a referência do gateway, sem cobrar."""
        ...
