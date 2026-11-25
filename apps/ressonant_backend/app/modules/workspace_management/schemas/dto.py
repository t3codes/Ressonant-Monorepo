import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ManagementLevel = Literal["read", "modify", "grant"]
TaxonomyKind = Literal["category", "version"]
CapabilityName = Literal[
    "management_read",
    "management_modify",
    "management_grant",
    "teams_create",
    "teams_update",
    "teams_soft_delete",
    "teams_hard_delete",
    "members_manage",
    "columns_manage",
    "blocked_cards_read",
    "blocked_cards_unblock",
    "audit_read",
    "settings_manage",
    "grants_manage",
    "taxonomy_read",
    "taxonomy_manage",
    "taxonomy_manage_grant",
]
CAPABILITY_NAMES: tuple[CapabilityName, ...] = (
    "management_read",
    "management_modify",
    "management_grant",
    "teams_create",
    "teams_update",
    "teams_soft_delete",
    "teams_hard_delete",
    "members_manage",
    "columns_manage",
    "blocked_cards_read",
    "blocked_cards_unblock",
    "audit_read",
    "settings_manage",
    "grants_manage",
    "taxonomy_read",
    "taxonomy_manage",
    "taxonomy_manage_grant",
)
# R9/R10, separação de poderes e regras duras de propriedade: nunca sobrescritas.
HARD_LOCKED_CAPABILITIES: tuple[CapabilityName, ...] = (
    "management_grant",
    "grants_manage",
    "settings_manage",
    "teams_hard_delete",
    "teams_soft_delete",
    "taxonomy_manage_grant",
    "taxonomy_manage",
    "taxonomy_read",
)
# Autorização positiva permanece no domínio; aqui `allow` é no-op e só `deny` veta.
DENY_ONLY_CAPABILITIES: tuple[CapabilityName, ...] = (
    "teams_create",
    "teams_update",
    "columns_manage",
    "blocked_cards_unblock",
)

_TAXONOMY_COLOR_RE = re.compile(r"(?:#[0-9a-fA-F]{6}|[A-Za-z0-9_-]{1,20})\Z")


def _validated_taxonomy_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or "<" in cleaned or ">" in cleaned:
        raise ValueError("nome inválido")
    return cleaned


def _validated_taxonomy_color(value: str | None) -> str | None:
    if value is None:
        return None
    if not _TAXONOMY_COLOR_RE.fullmatch(value):
        raise ValueError("cor inválida")
    return value


def _validated_taxonomy_user_id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("user_id inválido") from exc


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
    taxonomy_read: bool = False
    taxonomy_manage: bool = False
    taxonomy_manage_grant: bool = False


class ManagementAccessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    user_id: str
    is_owner: bool
    interno_adm: bool
    level: Literal["none", "read", "modify", "grant"]
    permission_version: int
    capabilities: ManagementCapabilities


class CapabilityOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: CapabilityName
    effect: Literal["allow", "deny"]


class TargetAccessResponse(ManagementAccessResponse):
    overrides: list[CapabilityOverride]
    editable: bool
    hard_locked_capabilities: list[CapabilityName]
    deny_only_capabilities: list[CapabilityName]


class CapabilityBatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: CapabilityName
    effect: Literal["allow", "deny", "reset"]


class CapabilityBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CapabilityBatchItem] = Field(max_length=17)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("items")
    @classmethod
    def _no_duplicates(cls, value: list[CapabilityBatchItem]) -> list[CapabilityBatchItem]:
        names = [item.capability for item in value]
        if len(set(names)) != len(names):
            raise ValueError("capability duplicada no lote")
        return value


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


class TaxonomyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TaxonomyKind
    name: str = Field(min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=20)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _validated_taxonomy_name(value)

    @field_validator("color")
    @classmethod
    def _color(cls, value: str | None) -> str | None:
        return _validated_taxonomy_color(value)


class TaxonomyPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color: str | None = Field(max_length=20)

    @field_validator("color")
    @classmethod
    def _color(cls, value: str | None) -> str | None:
        return _validated_taxonomy_color(value)


class TaxonomyDeactivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


class TaxonomyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    workspace_id: str
    kind: TaxonomyKind
    name: str
    color: str | None = None
    created_by_id: str | None = None
    criado_em: datetime
    atualizado_em: datetime
    desativado_em: datetime | None = None
    desativado_by_id: str | None = None


class TaxonomyGrantCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("user_id")
    @classmethod
    def _user_id(cls, value: str) -> str:
        return _validated_taxonomy_user_id(value)


class TaxonomyGrantRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


class TaxonomyGrantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    workspace_id: str
    user_id: str
    granted_by_id: str
    created_at: datetime
    updated_at: datetime
