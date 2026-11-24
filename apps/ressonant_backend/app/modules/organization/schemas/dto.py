from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

InvitationRole = Literal["admin", "member"]
InvitationStatus = Literal["pending", "accepted", "revoked", "expired", "declined"]


class InvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    nome_completo: str = Field(min_length=2, max_length=254)
    role: InvitationRole
    workspace_id: str = Field(min_length=1)
    team_id: str | None = None
    expires_in_days: int = Field(default=7, ge=1, le=30)


class InvitationCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    workspace_id: str
    email: str
    personal_email: str
    corporate_email: str
    invitee_name: str
    team_id: str | None = None
    team_name: str | None = None
    role: InvitationRole
    status: Literal["pending"] = "pending"
    expires_at: datetime
    invited_by_id: str
    criado_em: datetime
    token: str | None = None
    invite_url: str | None = None
    email_sent: bool = False
    email_delivery_status: str | None = None


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    organization_id: str
    workspace_id: str
    email: str
    personal_email: str
    corporate_email: str | None = None
    invitee_name: str | None = None
    team_id: str | None = None
    team_name: str | None = None
    reservation_active: bool = True
    role: str
    status: InvitationStatus
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    declined_at: datetime | None = None
    resent_at: datetime | None = None
    last_sent_at: datetime | None = None
    send_status: str | None = None
    invited_by_id: str
    criado_em: datetime


class InvitationPublicResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_name: str
    workspace_name: str
    team_name: str | None = None
    role: str
    email_masked: str
    expires_at: datetime
    status: InvitationStatus
    invited_by_name: str | None = None
    invitee_name: str | None = None
    corporate_email: str | None = None
    user_exists: bool = False


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


class InvitationResendResponse(InvitationResponse):
    token: str | None = None
    invite_url: str | None = None
    email_sent: bool = False
    email_delivery_status: str | None = None
