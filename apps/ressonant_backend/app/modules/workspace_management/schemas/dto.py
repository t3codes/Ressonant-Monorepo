from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ManagementLevel = Literal["read", "modify", "grant"]


class ManagementCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    management_read: bool = False
    management_modify: bool = False
    management_grant: bool = False
    teams_create: bool = False
    teams_update: bool = False
    teams_soft_delete: bool = False
    teams_hard_delete: bool = False
    members_manage: bool = False
    columns_manage: bool = False
    blocked_cards_read: bool = False
    blocked_cards_unblock: bool = False
    audit_read: bool = False
    settings_manage: bool = False
    grants_manage: bool = False


class ManagementAccessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    user_id: str
    is_owner: bool
    interno_adm: bool
    level: Literal["none", "read", "modify", "grant"]
    permission_version: int
    capabilities: ManagementCapabilities


class GrantCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)
    level: ManagementLevel
    reason: str | None = Field(default=None, max_length=500)


class GrantRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


class ManagementGrantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    user_id: str
    level: ManagementLevel
    granted_by_id: str
    reason: str | None = None
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None = None
    revoked_by_id: str | None = None
    revoke_reason: str | None = None
