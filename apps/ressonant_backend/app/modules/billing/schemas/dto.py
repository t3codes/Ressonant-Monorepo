from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    price_cents: int
    currency: str
    seat_limit: int | None = None
    overage: int | None = None
    trial_days: int
    active: bool


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["trialing", "active", "past_due", "canceled"]
    seats_purchased: int
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None
    gateway_ref: str | None = None
    provider: Literal["stub"] = "stub"


class BillingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str
    plan: PlanResponse
    subscription: SubscriptionResponse | None = None
    seats_used: int
    provider: Literal["stub"] = "stub"
    simulation: bool = True


class BillingUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str | None = Field(default=None, min_length=1, max_length=20)
    seats_purchased: int | None = Field(default=None, ge=0, le=10000)


class SubscriptionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str | None = Field(default=None, min_length=1, max_length=20)
    seats_purchased: int | None = Field(default=None, ge=0, le=10000)


class SubscriptionStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "past_due", "canceled"]
