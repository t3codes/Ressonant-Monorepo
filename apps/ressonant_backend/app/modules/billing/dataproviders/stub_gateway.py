import uuid

from app.modules.billing.domain.gateway import SubscriptionIntent


class StubBillingGateway:
    """Simulação local de gateway de pagamento: sem rede, SDK, segredo ou cobrança.

    O estado real da assinatura vive em ``subscriptions``; esta classe apenas
    confirma a intenção e devolve um ``gateway_ref`` sintético.
    """

    def create_subscription_intent(
        self, *, organization_id: str, plan_code: str, seats_purchased: int
    ) -> SubscriptionIntent:
        return SubscriptionIntent(gateway_ref=f"stub_{uuid.uuid4()}", confirmed=True)
