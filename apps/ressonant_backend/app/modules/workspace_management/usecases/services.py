from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, cast

from app.common.exceptions import ConflictException
from app.modules.teams.domain.models import TeamMember
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace
from app.modules.workspace_management.dataproviders.repository import WorkspaceManagementRepository
from app.modules.workspace_management.domain.models import (
    AuditEvent,
    CardTaxonomyModel,
    WorkspaceCapabilityGrant,
    WorkspaceManagementGrant,
    WorkspaceTaxonomyGrantModel,
)
from app.modules.workspace_management.schemas.dto import (
    CAPABILITY_NAMES,
    DENY_ONLY_CAPABILITIES,
    HARD_LOCKED_CAPABILITIES,
    CapabilityBatchItem,
    CapabilityOverride,
    ManagementAccessResponse,
    ManagementCapabilities,
    TargetAccessResponse,
)
from common.errors import (
    BadRequestException,
    ExceptionData,
    ForbiddenException,
    NotFoundException,
)

ManagementLevel = Literal["none", "read", "modify", "grant"]
LEVEL_RANK = {"none": 0, "read": 1, "modify": 2, "grant": 3}


@dataclass(frozen=True)
class ManagementAccess:
    workspace: Workspace
    user: User
    level: ManagementLevel
    is_owner: bool
    is_interno_adm: bool
    permission_version: int
    # Papel organizacional vem do repositório, nunca de `interno_adm`.
    organization_role: str | None = None
    is_member: bool = False
    capability_overrides: dict[str, str] = field(default_factory=dict)

    @property
    def has_inherent_access(self) -> bool:
        """Regras duras não podem ser sobrescritas por override granular."""
        return (
            self.is_owner
            or self.is_interno_adm
            or self.organization_role in {"owner", "billing_owner"}
        )

    @property
    def can_read(self) -> bool:
        return LEVEL_RANK[self.level] >= LEVEL_RANK["read"]

    @property
    def can_modify(self) -> bool:
        return LEVEL_RANK[self.level] >= LEVEL_RANK["modify"]

    @property
    def can_grant(self) -> bool:
        return LEVEL_RANK[self.level] >= LEVEL_RANK["grant"]

    @property
    def can_grant_grant_level(self) -> bool:
        """R9: só Dono da Empresa (por membership) ou interno_adm escalam para grant."""
        return self.is_interno_adm or self.organization_role == "owner"


class WorkspaceManagementService:
    def __init__(self, repo: WorkspaceManagementRepository) -> None:
        self._repo = repo

    @staticmethod
    def _not_found(message: str, error_code: str) -> NotFoundException:
        return NotFoundException(
            ExceptionData(message=message, error_code=error_code), is_expected=True
        )

    @staticmethod
    def _forbidden(
        message: str,
        *,
        error_code: str = "MANAGEMENT_ACCESS_DENIED",
        layer: str = "management",
        required: str | None = None,
    ) -> ForbiddenException:
        return ForbiddenException(
            ExceptionData(
                message=message,
                error_code=error_code,
                error_layer=layer,
                required_capability=required,
            ),
            is_expected=True,
        )

    @staticmethod
    def _conflict(message: str, error_code: str) -> ConflictException:
        return ConflictException(
            ExceptionData(message=message, error_code=error_code), is_expected=True
        )

    def _require_workspace(self, workspace_id: str) -> Workspace:
        ws = self._repo.get_workspace(workspace_id)
        if not ws:
            raise self._not_found("Workspace não encontrado", "WORKSPACE_NOT_FOUND")
        return ws

    def _is_member_operational(self, workspace: Workspace, user: User) -> bool:
        if workspace.owner_id == user.id:
            return True
        return self._repo.get_workspace_member(workspace.id, user.id) is not None

    @staticmethod
    def _redact(payload: dict | None) -> dict | None:
        if payload is None:
            return None
        sensitive = {
            "password",
            "senha",
            "token",
            "secret",
            "cpf",
            "telefone",
            "email",
            "authorization",
            "reason",
            "revoke_reason",
            "break_glass_reason",
        }

        def scrub(value: object) -> object:
            if isinstance(value, dict):
                return {
                    key: "[REDACTED]" if str(key).lower() in sensitive else scrub(item)
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [scrub(item) for item in value]
            return value

        return cast(dict, scrub(payload))

    def _audit(
        self,
        *,
        actor: User | None,
        action: str,
        entity_type: str,
        entity_id: str,
        workspace_id: str | None = None,
        organization_id: str | None = None,
        target_user_id: str | None = None,
        before: dict | None = None,
        after: dict | None = None,
        metadata: dict | None = None,
        result: str = "success",
        request_id: str | None = None,
        actor_role: str | None = None,
        permission_version: int | None = None,
        scope: Literal["organization", "workspace", "card"] = "workspace",
    ) -> None:
        actor_type = "system"
        actor_user_id = None
        if actor is not None:
            actor_user_id = actor.id
            actor_type = "internal_admin" if actor.interno_adm else "user"
        # Actor and role come from the authenticated caller, never from a request body.
        resolved_actor_role = actor_role if actor_role is not None else actor_type
        event = AuditEvent(
            workspace_id=workspace_id,
            organization_id=organization_id,
            scope=scope,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            actor_role=resolved_actor_role,
            permission_version=permission_version,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            target_user_id=target_user_id,
            request_id=request_id,
            before=self._redact(before),
            after=self._redact(after),
            metadata_=self._redact(metadata),
            result=result,
        )
        self._repo.add_audit_event(event)

    def _ensure_break_glass(
        self, workspace: Workspace, actor: User, reason: str | None, action: str
    ) -> dict | None:
        if not actor.interno_adm:
            return None
        if self._is_member_operational(workspace, actor):
            return {"interno_adm": True, "break_glass": False}
        if not reason or not reason.strip():
            raise self._forbidden(
                "Ação de interno_adm fora do workspace exige justificativa (break-glass).",
                error_code="BREAK_GLASS_REASON_REQUIRED",
                layer="management",
                required="management.break_glass_reason",
            )
        return {
            "interno_adm": True,
            "break_glass": True,
            "reason": reason.strip(),
            "action": action,
        }

    def resolve_access(self, workspace_id: str, user: User) -> ManagementAccess:
        """Combina os cinco eixos; papel vem de membership, nunca de `interno_adm`.

        `level == "grant"` autoriza gerenciar grants até `modify`; a escalada para
        nível `grant` é verificada à parte por `can_grant_grant_level` (R9).
        """
        workspace = self._require_workspace(workspace_id)
        is_owner = workspace.owner_id == user.id
        is_interno_adm = bool(user.interno_adm)
        organization_role = self._repo.get_organization_role(workspace.organization_id, user.id)
        member = self._repo.get_workspace_member(workspace_id, user.id)
        level: ManagementLevel = "none"
        if is_interno_adm or organization_role == "owner":
            level = "grant"
        elif (
            is_owner
            or organization_role == "admin"
            or (member is not None and member.role == "admin")
        ):
            # Dono/Admin de workspace e Admin da org concedem até modify (matriz §6).
            level = "grant"
        else:
            grant = self._repo.get_active_grant(workspace_id, user.id)
            if grant and grant.level in LEVEL_RANK:
                level = grant.level  # type: ignore[assignment]
        # Separação de poderes: Billing Owner não administra gestão de workspace.
        if organization_role == "billing_owner" and not is_interno_adm:
            level = "read" if level != "none" else "none"
        return ManagementAccess(
            workspace=workspace,
            user=user,
            level=level,
            is_owner=is_owner,
            is_interno_adm=is_interno_adm,
            permission_version=int(getattr(workspace, "management_permission_version", 1) or 1),
            organization_role=organization_role,
            is_member=member is not None,
            capability_overrides=self._repo.list_active_capability_overrides(workspace_id, user.id),
        )

    def build_capabilities(self, access: ManagementAccess) -> ManagementCapabilities:
        r, m, g = access.can_read, access.can_modify, access.can_grant
        is_owner_or_internal = access.can_grant_grant_level
        taxonomy_grant_authority = (
            access.is_owner or access.organization_role == "owner" or access.is_interno_adm
        )
        taxonomy_manager = (
            access.is_owner
            or access.organization_role == "owner"
            or access.is_interno_adm
            or self._repo.get_active_taxonomy_grant(access.workspace.id, access.user.id) is not None
        )
        capabilities = ManagementCapabilities(
            management_read=r,
            management_modify=m,
            management_grant=g,
            teams_create=m,
            teams_update=m,
            teams_soft_delete=m,
            teams_hard_delete=is_owner_or_internal,
            members_manage=m,
            columns_manage=m,
            blocked_cards_read=r,
            blocked_cards_unblock=m,  # still subject to domain policy at execution
            audit_read=r,
            settings_manage=is_owner_or_internal,
            grants_manage=g,
            taxonomy_read=access.is_owner or access.is_member,
            taxonomy_manage=taxonomy_manager,
            taxonomy_manage_grant=taxonomy_grant_authority,
        )
        # Regras duras (propriedade, separação de poderes, R9/R10) vêm primeiro e
        # nunca são sobrescritas por uma exceção granular.
        if access.has_inherent_access or not access.capability_overrides:
            return capabilities
        effective = capabilities.model_dump()
        for capability, effect in access.capability_overrides.items():
            if capability in HARD_LOCKED_CAPABILITIES or capability not in CAPABILITY_NAMES:
                continue
            if capability in DENY_ONLY_CAPABILITIES:
                effective[capability] = effective[capability] and effect != "deny"
            else:
                effective[capability] = effect == "allow"
        return ManagementCapabilities(**effective)

    def get_access_response(self, workspace_id: str, user: User) -> ManagementAccessResponse:
        access = self.resolve_access(workspace_id, user)
        return ManagementAccessResponse(
            workspace_id=access.workspace.id,
            user_id=user.id,
            is_owner=access.is_owner,
            interno_adm=access.is_interno_adm,
            level=access.level,
            permission_version=access.permission_version,
            capabilities=self.build_capabilities(access),
        )

    def _get_target_user(self, workspace: Workspace, target_user_id: str) -> User:
        target = self._repo.get_user(target_user_id)
        if target is None or (
            workspace.owner_id != target_user_id
            and self._repo.get_workspace_member(workspace.id, target_user_id) is None
        ):
            raise self._not_found(
                "Usuário alvo não encontrado no workspace", "WORKSPACE_MEMBER_NOT_FOUND"
            )
        return target

    def get_target_access(
        self, workspace_id: str, actor: User, target_user_id: str
    ) -> TargetAccessResponse:
        access = self.require_read(workspace_id, actor)
        can_view_overrides = self.build_capabilities(access).grants_manage
        target = self._get_target_user(access.workspace, target_user_id)
        target_access = self.resolve_access(workspace_id, target)
        editable = (
            can_view_overrides and target.id != actor.id and not target_access.has_inherent_access
        )
        overrides = (
            [
                CapabilityOverride(capability=capability, effect=effect)
                for capability, effect in sorted(target_access.capability_overrides.items())
            ]
            if can_view_overrides
            else []
        )
        return TargetAccessResponse(
            workspace_id=access.workspace.id,
            user_id=target.id,
            is_owner=target_access.is_owner,
            interno_adm=target_access.is_interno_adm,
            level=target_access.level,
            permission_version=target_access.permission_version,
            capabilities=self.build_capabilities(target_access),
            overrides=overrides,
            editable=editable,
            hard_locked_capabilities=(
                list(HARD_LOCKED_CAPABILITIES) if editable else list(CAPABILITY_NAMES)
            ),
            deny_only_capabilities=list(DENY_ONLY_CAPABILITIES),
        )

    def update_capabilities(
        self,
        workspace_id: str,
        actor: User,
        target_user_id: str,
        *,
        items: list[CapabilityBatchItem],
        reason: str | None = None,
        request_id: str | None = None,
    ) -> TargetAccessResponse:
        access = self.require_read(workspace_id, actor)
        if not self.build_capabilities(access).grants_manage:
            raise self._forbidden(
                "Você não tem permissão para alterar capabilities.",
                required="management.grants_manage",
            )
        if target_user_id == actor.id:
            raise self._forbidden(
                "Um usuário não pode alterar suas próprias permissões.",
                error_code="SELF_PERMISSION_CHANGE_FORBIDDEN",
                required="management.grants_manage",
            )
        target = self._get_target_user(access.workspace, target_user_id)
        target_access = self.resolve_access(workspace_id, target)
        if target_access.has_inherent_access:
            raise self._forbidden(
                "As permissões deste usuário são inerentes ao seu papel.",
                error_code="TARGET_ACCESS_INHERENT",
                required="management.grants_manage",
            )
        # `reason` só valida o break-glass: nunca entra em log, auditoria ou resposta.
        self._taxonomy_break_glass(access, reason=reason)
        current = target_access.capability_overrides
        before: dict[str, str] = {}
        after: dict[str, str] = {}
        planned: list[tuple[str, str, WorkspaceCapabilityGrant | None]] = []
        for item in items:
            if item.capability not in CAPABILITY_NAMES:
                raise BadRequestException(
                    ExceptionData(
                        message="Capability inválida no lote", error_code="CAPABILITY_INVALID"
                    ),
                    is_expected=True,
                )
            if item.effect == "allow" and item.capability in DENY_ONLY_CAPABILITIES:
                raise BadRequestException(
                    ExceptionData(
                        message="Esta capability só aceita deny ou reset.",
                        error_code="CAPABILITY_DENY_ONLY",
                    ),
                    is_expected=True,
                )
            if item.capability in HARD_LOCKED_CAPABILITIES:
                raise self._forbidden(
                    "Esta capability é protegida por regra dura.",
                    error_code="CAPABILITY_PROTECTED",
                    required="management.grants_manage",
                )
            before[item.capability] = current.get(item.capability, "none")
            after[item.capability] = item.effect
            planned.append(
                (
                    item.capability,
                    item.effect,
                    self._repo.get_active_capability_override(
                        workspace_id, target_user_id, item.capability
                    ),
                )
            )
        try:
            for capability, effect, existing in planned:
                if effect == "reset":
                    if existing is not None:
                        self._repo.revoke_capability_override(existing, revoked_by_id=actor.id)
                elif existing is not None:
                    existing.effect = effect
                    existing.granted_by_id = actor.id
                    existing.updated_at = datetime.now(UTC)
                    self._repo.add_capability_override(existing)
                else:
                    self._repo.add_capability_override(
                        WorkspaceCapabilityGrant(
                            workspace_id=workspace_id,
                            user_id=target_user_id,
                            capability=capability,
                            effect=effect,
                            granted_by_id=actor.id,
                        )
                    )
            version = self._repo.bump_permission_version_atomic(workspace_id)
            self._audit(
                workspace_id=workspace_id,
                actor=actor,
                action="capability_override.batch",
                entity_type="workspace_capability_grant",
                entity_id=target_user_id,
                target_user_id=target_user_id,
                before=before,
                after=after,
                metadata=None,
                request_id=request_id,
                actor_role=access.organization_role,
                permission_version=version,
            )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return self.get_target_access(workspace_id, actor, target_user_id)

    def require_read(self, workspace_id: str, user: User) -> ManagementAccess:
        access = self.resolve_access(workspace_id, user)
        if not self.build_capabilities(access).management_read:
            raise self._forbidden(
                "Você não tem permissão de leitura na gestão deste workspace.",
                required="management.read",
            )
        return access

    def require_modify(self, workspace_id: str, user: User) -> ManagementAccess:
        access = self.resolve_access(workspace_id, user)
        if not self.build_capabilities(access).management_modify:
            raise self._forbidden(
                "Você não tem permissão de modificação na gestão deste workspace.",
                required="management.modify",
            )
        return access

    def require_grant(self, workspace_id: str, user: User) -> ManagementAccess:
        access = self.resolve_access(workspace_id, user)
        if not self.build_capabilities(access).management_grant:
            raise self._forbidden(
                "Você não tem permissão para gerenciar grants da gestão.",
                required="management.grant",
            )
        return access

    def _require_capability(self, access: ManagementAccess, capability: str, required: str) -> None:
        """Checkpoint específico: a capability efetiva, não só o nível MG, decide."""
        if not getattr(self.build_capabilities(access), capability):
            raise self._forbidden(
                "Você não tem permissão para esta ação de gestão.", required=required
            )

    def list_grants(self, workspace_id: str, actor: User) -> list[WorkspaceManagementGrant]:
        self.require_read(workspace_id, actor)
        return self._repo.list_active_grants(workspace_id)

    def create_or_update_grant(
        self,
        workspace_id: str,
        actor: User,
        *,
        target_user_id: str,
        level: str,
        reason: str | None = None,
        request_id: str | None = None,
    ) -> WorkspaceManagementGrant:
        access = self.require_grant(workspace_id, actor)
        self._require_capability(access, "grants_manage", "management.grants_manage")
        if target_user_id == actor.id:
            raise self._forbidden(
                "Um usuário não pode alterar suas próprias permissões.",
                error_code="SELF_PERMISSION_CHANGE_FORBIDDEN",
                required="management.grants_manage",
            )
        workspace = access.workspace
        if level not in ("read", "modify", "grant"):
            raise self._conflict("Nível de grant inválido", "MANAGEMENT_GRANT_INVALID_LEVEL")
        # R9: only owner/interno_adm can grant 'grant'
        if level == "grant" and not access.can_grant_grant_level:
            raise self._forbidden(
                "Apenas owner ou interno_adm podem conceder nível grant.",
                error_code="MANAGEMENT_GRANT_ESCALATION_DENIED",
                required="management.grant.grant",
            )
        # target must be workspace member? plan says "qualquer usuário do workspace" - we'll require
        # they exist as user? at least check not self weird cases; better require workspace member
        if (
            not self._is_member_operational(
                workspace,
                User(
                    id=target_user_id,
                    email="",
                    senha_hash="",
                    cpf="",
                    idade=0,
                    termos_contrato=True,
                    interno_adm=False,
                    status_ativo=True,
                ),
            )
            and self._repo.get_workspace_member(workspace_id, target_user_id) is None
        ):
            # owner is operational; for target, just check membership by repo
            pass
        target_member = self._repo.get_workspace_member(workspace_id, target_user_id)
        if workspace.owner_id != target_user_id and target_member is None:
            raise self._not_found(
                "Usuário alvo não é membro do workspace", "WORKSPACE_MEMBER_NOT_FOUND"
            )

        break_glass = self._ensure_break_glass(workspace, actor, reason, "management.grant.upsert")
        existing = self._repo.get_active_grant(workspace_id, target_user_id)
        before = {"level": existing.level} if existing else None
        try:
            if existing:
                existing.level = level
                existing.granted_by_id = actor.id
                existing.reason = reason
                grant = existing
                self._repo.add_grant(grant)  # flush
            else:
                grant = WorkspaceManagementGrant(
                    workspace_id=workspace_id,
                    user_id=target_user_id,
                    level=level,
                    granted_by_id=actor.id,
                    reason=reason,
                )
                self._repo.add_grant(grant)
            self._repo.bump_permission_version(workspace_id)
            self._audit(
                workspace_id=workspace_id,
                actor=actor,
                action="management.grant.upsert",
                entity_type="workspace_management_grant",
                entity_id=grant.id,
                target_user_id=target_user_id,
                before=before,
                after={"level": level},
                metadata=break_glass,
                request_id=request_id,
                actor_role=access.organization_role,
            )
            self._repo.commit()
            return grant
        except Exception:
            self._repo.rollback()
            raise

    def revoke_grant(
        self,
        workspace_id: str,
        actor: User,
        *,
        target_user_id: str,
        reason: str | None = None,
        request_id: str | None = None,
    ) -> None:
        access = self.require_grant(workspace_id, actor)
        self._require_capability(access, "grants_manage", "management.grants_manage")
        if target_user_id == actor.id:
            raise self._forbidden(
                "Um usuário não pode alterar suas próprias permissões.",
                error_code="SELF_PERMISSION_CHANGE_FORBIDDEN",
                required="management.grants_manage",
            )
        workspace = access.workspace
        break_glass = self._ensure_break_glass(workspace, actor, reason, "management.grant.revoke")
        grant = self._repo.get_active_grant(workspace_id, target_user_id)
        if not grant:
            raise self._not_found("Grant de gestão não encontrado", "MANAGEMENT_GRANT_NOT_FOUND")
        # R9: revoking grant-level grant requires owner/interno_adm
        if grant.level == "grant" and not access.can_grant_grant_level:
            raise self._forbidden(
                "Apenas owner ou interno_adm podem revogar nível grant.",
                error_code="MANAGEMENT_GRANT_ESCALATION_DENIED",
                required="management.grant.grant",
            )
        before = {"level": grant.level}
        try:
            self._repo.revoke_grant(grant, revoked_by_id=actor.id, revoke_reason=reason)
            self._repo.bump_permission_version(workspace_id)
            self._audit(
                workspace_id=workspace_id,
                actor=actor,
                action="management.grant.revoke",
                entity_type="workspace_management_grant",
                entity_id=grant.id,
                target_user_id=target_user_id,
                before=before,
                after={"revoked": True},
                metadata=break_glass,
                request_id=request_id,
                actor_role=access.organization_role,
            )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise

    def list_people(self, workspace_id: str, actor: User):
        self.require_read(workspace_id, actor)
        return self._repo.list_workspace_members(workspace_id)

    def get_person(self, workspace_id: str, actor: User, target_user_id: str):
        self.require_read(workspace_id, actor)
        person = self._repo.get_workspace_person(workspace_id, target_user_id)
        if person is None:
            raise self._not_found(
                "Pessoa não encontrada no workspace", "WORKSPACE_MEMBER_NOT_FOUND"
            )
        return person

    def remove_person(
        self,
        workspace_id: str,
        actor: User,
        target_user_id: str,
        *,
        reason: str | None = None,
        request_id: str | None = None,
    ) -> None:
        access = self.require_modify(workspace_id, actor)
        self._require_capability(access, "members_manage", "management.members_manage")
        if target_user_id == actor.id:
            raise self._forbidden(
                "Um usuário não pode remover a si mesmo do workspace.",
                error_code="SELF_PERMISSION_CHANGE_FORBIDDEN",
                required="management.members_manage",
            )
        workspace = access.workspace
        break_glass = self._ensure_break_glass(workspace, actor, reason, "management.person.remove")
        member = self._repo.get_workspace_member(workspace_id, target_user_id)
        if member is None:
            raise self._not_found(
                "Pessoa não encontrada no workspace", "WORKSPACE_MEMBER_NOT_FOUND"
            )
        if workspace.owner_id == target_user_id:
            raise self._conflict(
                "O proprietário do workspace não pode ser removido pelo painel de gestão.",
                "WORKSPACE_OWNER_CANNOT_BE_REMOVED",
            )
        target_role = self._repo.get_organization_role(workspace.organization_id, target_user_id)
        if target_role == "owner" and not actor.interno_adm:
            raise self._forbidden(
                "Apenas interno_adm pode remover um dono da organização do workspace.",
                required="management.owner_remove",
            )
        try:
            team_memberships = self._repo.list_workspace_team_memberships(
                workspace_id, target_user_id
            )
            removed_team_ids = [tm.team_id for tm in team_memberships]
            for tm in team_memberships:
                self._repo.remove_team_member(tm)
            self._repo.remove_workspace_member(member)
            self._repo.bump_permission_version(workspace_id)
            self._audit(
                workspace_id=workspace_id,
                actor=actor,
                action="management.person.removed",
                entity_type="workspace_member",
                entity_id=target_user_id,
                target_user_id=target_user_id,
                before={"role": member.role, "team_ids": removed_team_ids},
                after={"removed": True},
                metadata=break_glass,
                request_id=request_id,
                actor_role=access.organization_role,
                permission_version=access.permission_version,
            )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise

    def change_person_team(
        self,
        workspace_id: str,
        actor: User,
        target_user_id: str,
        *,
        target_team_id: str,
        from_team_id: str | None = None,
        reason: str | None = None,
        request_id: str | None = None,
    ):
        access = self.require_modify(workspace_id, actor)
        self._require_capability(access, "members_manage", "management.members_manage")
        workspace = access.workspace
        break_glass = self._ensure_break_glass(
            workspace, actor, reason, "management.person.team_change"
        )
        member = self._repo.get_workspace_member(workspace_id, target_user_id)
        if member is None:
            raise self._not_found(
                "Pessoa não encontrada no workspace", "WORKSPACE_MEMBER_NOT_FOUND"
            )
        target_team = self._repo.get_team(target_team_id)
        if (
            target_team is None
            or target_team.workspace_id != workspace_id
            or target_team.is_deleted
        ):
            raise self._not_found("Equipe não encontrada", "TEAM_NOT_FOUND")
        if from_team_id:
            from_team = self._repo.get_team(from_team_id)
            if from_team is None or from_team.workspace_id != workspace_id:
                raise self._not_found("Equipe de origem não encontrada", "TEAM_NOT_FOUND")
            from_member = self._repo.get_team_member(from_team_id, target_user_id)
            if from_member is None:
                raise self._conflict(
                    "Usuário não pertence à equipe de origem informada.",
                    "TEAM_MEMBER_NOT_FOUND",
                )
        try:
            removed_from = []
            if from_team_id:
                from_member = self._repo.get_team_member(from_team_id, target_user_id)
                if from_member is not None:
                    self._repo.remove_team_member(from_member)
                    removed_from.append(from_team_id)
            existing_target = self._repo.get_team_member(target_team_id, target_user_id)
            added = False
            target_role = "admin" if member.role == "admin" else "member"
            if existing_target is None:
                self._repo.add_team_member(
                    TeamMember(team_id=target_team_id, user_id=target_user_id, role=target_role)
                )
                added = True
            self._audit(
                workspace_id=workspace_id,
                actor=actor,
                action="management.person.team_changed",
                entity_type="workspace_member",
                entity_id=target_user_id,
                target_user_id=target_user_id,
                before={"from_team_id": from_team_id},
                after={
                    "target_team_id": target_team_id,
                    "removed_from": removed_from,
                    "added": added,
                },
                metadata=break_glass,
                request_id=request_id,
                actor_role=access.organization_role,
                permission_version=access.permission_version,
            )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        person = self._repo.get_workspace_person(workspace_id, target_user_id)
        if person is None:
            raise self._not_found(
                "Pessoa não encontrada no workspace", "WORKSPACE_MEMBER_NOT_FOUND"
            )
        return person

    def list_teams(self, workspace_id: str, actor: User, include_deleted: bool = False):
        self.require_read(workspace_id, actor)
        teams = self._repo.list_teams(workspace_id, include_deleted=include_deleted)
        return [
            {
                "id": t.id,
                "workspace_id": t.workspace_id,
                "name": t.name,
                "slug": t.slug,
                "description": t.description,
                "status_ativo": t.status_ativo,
                "is_deleted": t.is_deleted,
                "deleted_at": t.deleted_at,
                "members_count": self._repo.count_team_members(t.id),
            }
            for t in teams
        ]

    def list_audit(self, workspace_id: str, actor: User, skip: int = 0, limit: int = 50):
        access = self.require_read(workspace_id, actor)
        self._require_capability(access, "audit_read", "management.audit_read")
        events = self._repo.list_audit_events(workspace_id, skip=skip, limit=limit)
        return [
            {
                "id": e.id,
                "workspace_id": e.workspace_id,
                "organization_id": e.organization_id,
                "scope": e.scope,
                "occurred_at": e.occurred_at,
                "actor_user_id": e.actor_user_id,
                "actor_type": e.actor_type,
                "actor_role": e.actor_role,
                "permission_version": e.permission_version,
                "action": e.action,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "target_user_id": e.target_user_id,
                "request_id": e.request_id,
                "before": e.before,
                "after": e.after,
                "metadata": e.metadata_,
                "result": e.result,
            }
            for e in events
        ]

    def list_blocked_cards(self, workspace_id: str, actor: User):
        access = self.require_read(workspace_id, actor)
        self._require_capability(access, "blocked_cards_read", "management.blocked_cards_read")
        cards = self._repo.list_blocked_cards(workspace_id)
        return [
            {
                "id": c.id,
                "title": c.title,
                "team_id": c.team_id,
                "board_id": c.board_id,
                "column_id": c.column_id,
                "block_reason": c.block_reason,
                "blocked_by": c.blocked_by,
                "blocked_at": c.blocked_at,
            }
            for c in cards
        ]

    @staticmethod
    def _valid_uuid(value: str) -> bool:
        try:
            uuid.UUID(value)
            return True
        except (ValueError, AttributeError, TypeError):
            return False

    @staticmethod
    def _taxonomy_not_found() -> NotFoundException:
        return NotFoundException(
            ExceptionData(
                message="Recurso de taxonomia não encontrado",
                error_code="TAXONOMY_NOT_FOUND",
            ),
            is_expected=True,
        )

    def _is_taxonomy_member(self, workspace: Workspace, user_id: str) -> bool:
        return workspace.owner_id == user_id or (
            self._valid_uuid(user_id)
            and self._repo.get_workspace_member(workspace.id, user_id) is not None
        )

    def require_taxonomy_read(self, workspace_id: str, user: User) -> ManagementAccess:
        access = self.resolve_access(workspace_id, user)
        if not self.build_capabilities(access).taxonomy_read:
            raise self._forbidden(
                "Você não tem permissão para ler a taxonomia deste workspace.",
                error_code="TAXONOMY_ACCESS_DENIED",
                required="taxonomy.read",
            )
        return access

    def require_taxonomy_manage(self, workspace_id: str, user: User) -> ManagementAccess:
        access = self.resolve_access(workspace_id, user)
        if not self.build_capabilities(access).taxonomy_manage:
            raise self._forbidden(
                "Você não tem permissão para gerenciar a taxonomia deste workspace.",
                error_code="TAXONOMY_ACCESS_DENIED",
                required="taxonomy.manage",
            )
        return access

    def require_taxonomy_manage_grant(self, workspace_id: str, user: User) -> ManagementAccess:
        access = self.resolve_access(workspace_id, user)
        if not self.build_capabilities(access).taxonomy_manage_grant:
            raise self._forbidden(
                "Você não tem permissão para conceder ou revogar grants de taxonomia.",
                error_code="TAXONOMY_GRANT_DENIED",
                required="taxonomy.manage.grant",
            )
        return access

    def _taxonomy_break_glass(self, access: ManagementAccess, *, reason: str | None) -> bool:
        """R10 sem texto livre: `reason` só valida, nunca entra em audit/log."""
        if not access.user.interno_adm:
            return False
        if self._is_taxonomy_member(access.workspace, access.user.id):
            return False
        if not reason or not reason.strip():
            raise self._forbidden(
                "Ação de interno_adm fora do workspace exige justificativa (break-glass).",
                error_code="BREAK_GLASS_REASON_REQUIRED",
                required="management.break_glass_reason",
            )
        return True

    def _audit_taxonomy(
        self,
        *,
        access: ManagementAccess,
        action: str,
        entity_type: str,
        entity_id: str,
        after: dict[str, bool],
        permission_version: int,
        request_id: str | None = None,
        target_user_id: str | None = None,
        break_glass: bool = False,
    ) -> None:
        """Só IDs, booleanos, entity_type e permission_version — nunca texto livre."""
        workspace_id = access.workspace.id
        actor_type = "internal_admin" if access.user.interno_adm else "user"
        truncated_request_id = (request_id or "")[:100] or None
        event = AuditEvent(
            workspace_id=workspace_id,
            actor_user_id=access.user.id,
            actor_type=actor_type,
            actor_role=access.organization_role or actor_type,
            permission_version=permission_version,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            target_user_id=target_user_id,
            request_id=truncated_request_id,
            before=None,
            after=after,
            metadata_=None,
            result="success",
        )
        self._repo.add_audit_event(event)
        if break_glass:
            self._repo.add_audit_event(
                AuditEvent(
                    workspace_id=workspace_id,
                    actor_user_id=access.user.id,
                    actor_type=actor_type,
                    actor_role=access.organization_role or actor_type,
                    permission_version=permission_version,
                    action="break_glass",
                    entity_type=entity_type,
                    entity_id=entity_id,
                    target_user_id=target_user_id,
                    request_id=truncated_request_id,
                    before=None,
                    after={"break_glass": True},
                    metadata_=None,
                    result="success",
                )
            )

    def list_taxonomy(
        self,
        workspace_id: str,
        actor: User,
        *,
        kind: Literal["category", "version"],
        include_inactive: bool = False,
    ) -> list[CardTaxonomyModel]:
        access = self.require_taxonomy_read(workspace_id, actor)
        if include_inactive and not self.build_capabilities(access).taxonomy_manage:
            raise self._forbidden(
                "Somente gestores podem listar valores de taxonomia desativados.",
                error_code="TAXONOMY_ACCESS_DENIED",
                required="taxonomy.manage",
            )
        return self._repo.list_taxonomy(workspace_id, kind=kind, include_inactive=include_inactive)

    def create_taxonomy(
        self,
        workspace_id: str,
        actor: User,
        *,
        kind: Literal["category", "version"],
        name: str,
        color: str | None = None,
        request_id: str | None = None,
        break_glass_reason: str | None = None,
    ) -> CardTaxonomyModel:
        access = self.require_taxonomy_manage(workspace_id, actor)
        break_glass = self._taxonomy_break_glass(access, reason=break_glass_reason)
        item = CardTaxonomyModel(
            workspace_id=workspace_id,
            kind=kind,
            name=name,
            color=color,
            created_by_id=actor.id,
        )
        try:
            item = self._repo.add_taxonomy(item)
            version = self._repo.bump_permission_version(workspace_id)
            self._audit_taxonomy(
                access=access,
                action="taxonomy.created",
                entity_type="card_taxonomy",
                entity_id=item.id,
                after={"created": True},
                permission_version=version,
                request_id=request_id,
                break_glass=break_glass,
            )
            self._repo.commit()
            return item
        except Exception:
            self._repo.rollback()
            raise

    def patch_taxonomy_color(
        self,
        workspace_id: str,
        actor: User,
        taxonomy_id: str,
        *,
        color: str | None,
        request_id: str | None = None,
        break_glass_reason: str | None = None,
    ) -> CardTaxonomyModel:
        access = self.require_taxonomy_manage(workspace_id, actor)
        if not self._valid_uuid(taxonomy_id):
            raise self._taxonomy_not_found()
        item = self._repo.get_taxonomy(workspace_id, taxonomy_id)
        if item is None or item.desativado_em is not None:
            raise self._taxonomy_not_found()
        break_glass = self._taxonomy_break_glass(access, reason=break_glass_reason)
        try:
            item.color = color
            version = self._repo.bump_permission_version(workspace_id)
            self._audit_taxonomy(
                access=access,
                action="taxonomy.color_changed",
                entity_type="card_taxonomy",
                entity_id=item.id,
                after={"color_changed": True},
                permission_version=version,
                request_id=request_id,
                break_glass=break_glass,
            )
            self._repo.commit()
            return item
        except Exception:
            self._repo.rollback()
            raise

    def deactivate_taxonomy(
        self,
        workspace_id: str,
        actor: User,
        taxonomy_id: str,
        *,
        reason: str | None = None,
        request_id: str | None = None,
        break_glass_reason: str | None = None,
    ) -> CardTaxonomyModel:
        access = self.require_taxonomy_manage(workspace_id, actor)
        if not self._valid_uuid(taxonomy_id):
            raise self._taxonomy_not_found()
        item = self._repo.get_taxonomy(workspace_id, taxonomy_id)
        if item is None or item.desativado_em is not None:
            raise self._taxonomy_not_found()
        break_glass = self._taxonomy_break_glass(access, reason=break_glass_reason)
        try:
            self._repo.deactivate_taxonomy(item, deactivated_by_id=actor.id, reason=reason)
            version = self._repo.bump_permission_version(workspace_id)
            self._audit_taxonomy(
                access=access,
                action="taxonomy.deactivated",
                entity_type="card_taxonomy",
                entity_id=item.id,
                after={"deactivated": True},
                permission_version=version,
                request_id=request_id,
                break_glass=break_glass,
            )
            self._repo.commit()
            return item
        except Exception:
            self._repo.rollback()
            raise

    def list_taxonomy_grants(
        self, workspace_id: str, actor: User
    ) -> list[WorkspaceTaxonomyGrantModel]:
        self.require_taxonomy_manage(workspace_id, actor)
        return self._repo.list_active_taxonomy_grants(workspace_id)

    def grant_taxonomy(
        self,
        workspace_id: str,
        actor: User,
        *,
        target_user_id: str,
        reason: str | None = None,
        request_id: str | None = None,
    ) -> WorkspaceTaxonomyGrantModel:
        access = self.require_taxonomy_manage_grant(workspace_id, actor)
        if not self._valid_uuid(target_user_id):
            raise self._taxonomy_not_found()
        if not self._is_taxonomy_member(access.workspace, target_user_id):
            raise self._taxonomy_not_found()
        break_glass = self._taxonomy_break_glass(access, reason=reason)
        if self._repo.get_active_taxonomy_grant(workspace_id, target_user_id) is not None:
            raise self._conflict(
                "Grant de taxonomia já está ativo", "TAXONOMY_GRANT_ALREADY_ACTIVE"
            )
        grant = WorkspaceTaxonomyGrantModel(
            workspace_id=workspace_id,
            user_id=target_user_id,
            granted_by_id=actor.id,
            reason=reason,
        )
        try:
            grant = self._repo.add_taxonomy_grant(grant)
            version = self._repo.bump_permission_version(workspace_id)
            self._audit_taxonomy(
                access=access,
                action="taxonomy.grant.created",
                entity_type="workspace_taxonomy_grant",
                entity_id=grant.id,
                after={"granted": True},
                permission_version=version,
                request_id=request_id,
                target_user_id=target_user_id,
                break_glass=break_glass,
            )
            self._repo.commit()
            return grant
        except Exception:
            self._repo.rollback()
            raise

    def revoke_taxonomy_grant(
        self,
        workspace_id: str,
        actor: User,
        *,
        target_user_id: str,
        reason: str | None = None,
        request_id: str | None = None,
    ) -> None:
        access = self.require_taxonomy_manage_grant(workspace_id, actor)
        if not self._valid_uuid(target_user_id):
            raise self._taxonomy_not_found()
        if not self._is_taxonomy_member(access.workspace, target_user_id):
            raise self._taxonomy_not_found()
        grant = self._repo.get_active_taxonomy_grant(workspace_id, target_user_id)
        if grant is None:
            raise self._taxonomy_not_found()
        break_glass = self._taxonomy_break_glass(access, reason=reason)
        try:
            self._repo.revoke_taxonomy_grant(grant, revoked_by_id=actor.id, revoke_reason=reason)
            version = self._repo.bump_permission_version(workspace_id)
            self._audit_taxonomy(
                access=access,
                action="taxonomy.grant.revoked",
                entity_type="workspace_taxonomy_grant",
                entity_id=grant.id,
                after={"revoked": True},
                permission_version=version,
                request_id=request_id,
                target_user_id=target_user_id,
                break_glass=break_glass,
            )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
