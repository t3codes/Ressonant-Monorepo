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


class WorkspacePersonResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    role: str
    name: str | None = None
    email: str | None = None
    criado_em: datetime | None = None


class WorkspacePersonTeamResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: str
    team_name: str
    team_role: str


class WorkspacePersonDetailResponse(WorkspacePersonResponse):
    teams: list[WorkspacePersonTeamResponse] = Field(default_factory=list)


class WorkspacePersonTeamChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_team_id: str = Field(min_length=1)
    from_team_id: str | None = Field(default=None, min_length=1)


class AdminTeamResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    workspace_id: str
    name: str
    slug: str
    description: str | None = None
    status_ativo: bool
    is_deleted: bool = False
    deleted_at: datetime | None = None
    members_count: int = 0


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    workspace_id: str | None = None
    organization_id: str | None = None
    scope: Literal["organization", "workspace", "card"] = "workspace"
    occurred_at: datetime
    actor_user_id: str | None = None
    actor_type: str
    actor_role: str | None = None
    permission_version: int | None = None
    action: str
    entity_type: str
    entity_id: str
    target_user_id: str | None = None
    request_id: str | None = None
    before: dict | None = None
    after: dict | None = None
    metadata: dict | None = None
    result: str | None = None


class BlockedCardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    team_id: str | None = None
    board_id: str | None = None
    column_id: str | None = None
    block_reason: str | None = None
    blocked_by: str | None = None
    blocked_at: datetime | None = None
