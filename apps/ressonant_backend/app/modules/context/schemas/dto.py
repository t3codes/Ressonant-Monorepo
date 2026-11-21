from datetime import datetime
from typing import Literal

from app.modules.user.schemas import UserResponse
from app.modules.workspace_management.schemas.dto import ManagementCapabilities
from pydantic import BaseModel, ConfigDict


class OrganizationContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    slug: str
    role: str
    status: str


class TeamContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    slug: str
    key_prefix: str
    role: str


class WorkspaceContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    slug: str
    organization_id: str
    role: str
    member_ids: list[str]
    teams: list[TeamContextResponse]
    capabilities: ManagementCapabilities
    permission_version: int


class BillingCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    view: bool
    manage: bool


class DomainCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cards_write: bool


class ContextCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    management: ManagementCapabilities
    billing: BillingCapabilities
    domain: DomainCapabilities


class SubscriptionContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str
    plan_name: str
    status: str
    seats_purchased: int
    seat_limit: int | None
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    price_cents: int
    overage_cents_per_seat: int | None
    provider: Literal["stub"] = "stub"


class MeContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: UserResponse
    organizations: list[OrganizationContextResponse]
    active_organization: OrganizationContextResponse | None
    workspaces: list[WorkspaceContextResponse]
    capabilities: ContextCapabilities
    subscription: SubscriptionContextResponse | None
    permission_version: int
