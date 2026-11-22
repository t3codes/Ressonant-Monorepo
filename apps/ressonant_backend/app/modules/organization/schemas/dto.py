from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

InvitationRole = Literal["admin", "member"]
InvitationStatus = Literal["pending", "accepted", "revoked", "expired"]


class InvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: InvitationRole
    workspace_id: str = Field(min_length=1)
    expires_in_days: int = Field(default=7, ge=1, le=30)


class InvitationCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    workspace_id: str
    email: str
    role: InvitationRole
    status: Literal["pending"] = "pending"
    expires_at: datetime
    invited_by_id: str
    criado_em: datetime
    # Returned only at creation time so the caller can deliver it out-of-band.
    token: str
    invite_url: str | None = None
    email_sent: bool = False


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    organization_id: str
    workspace_id: str
    email: str
    role: str
    status: InvitationStatus
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    invited_by_id: str
    criado_em: datetime


class InvitationAcceptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    workspace_id: str
    email: str
    role: str
    status: Literal["accepted"] = "accepted"
    accepted_at: datetime
    organization_member_created: bool
    workspace_member_created: bool
