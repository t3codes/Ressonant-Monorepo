from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from common.errors import ExceptionData, ForbiddenException, NotFoundException
from app.common.exceptions import ConflictException

from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace
from app.modules.workspace_management.dataproviders.repository import WorkspaceManagementRepository
from app.modules.workspace_management.domain.models import AuditEvent, WorkspaceManagementGrant
from app.modules.workspace_management.schemas.dto import ManagementAccessResponse, ManagementCapabilities


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

    @property
    def can_read(self) -> bool:
        return LEVEL_RANK[self.level] >= LEVEL_RANK["read"]

    @property
    def can_modify(self) -> bool:
        return LEVEL_RANK[self.level] >= LEVEL_RANK["modify"]

    @property
    def can_grant(self) -> bool:
        return LEVEL_RANK[self.level] >= LEVEL_RANK["grant"]


class WorkspaceManagementService:
    def __init__(self, repo: WorkspaceManagementRepository) -> None:
        self._repo = repo

    @staticmethod
    def _not_found(message: str, error_code: str) -> NotFoundException:
        return NotFoundException(ExceptionData(message=message, error_code=error_code), is_expected=True)

    @staticmethod
    def _forbidden(message: str, *, error_code: str = "MANAGEMENT_ACCESS_DENIED", layer: str = "management", required: str | None = None) -> ForbiddenException:
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
        return ConflictException(ExceptionData(message=message, error_code=error_code), is_expected=True)

    def _require_workspace(self, workspace_id: str) -> Workspace:
        ws = self._repo.get_workspace(workspace_id)
        if not ws:
            raise self._not_found("Workspace não encontrado", "WORKSPACE_NOT_FOUND")
        return ws

    def _is_member_operational(self, workspace: Workspace, user: User) -> bool:
        if workspace.owner_id == user.id:
            return True
        return self._repo.get_workspace_member(workspace.id, user.id) is not None

    def _audit(
        self,
        *,
        workspace_id: str,
        actor: User | None,
        action: str,
        entity_type: str,
        entity_id: str,
        target_user_id: str | None = None,
        before: dict | None = None,
        after: dict | None = None,
        metadata: dict | None = None,
        result: str = "success",
        request_id: str | None = None,
    ) -> None:
        actor_type = "system"
        actor_user_id = None
        if actor is not None:
            actor_user_id = actor.id
            actor_type = "internal_admin" if actor.interno_adm else "user"
        event = AuditEvent(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            target_user_id=target_user_id,
            request_id=request_id,
            before=before,
            after=after,
            metadata_=metadata,
            result=result,
        )
        self._repo.add_audit_event(event)

    def _ensure_break_glass(self, workspace: Workspace, actor: User, reason: str | None, action: str) -> dict | None:
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
        return {"interno_adm": True, "break_glass": True, "reason": reason.strip(), "action": action}

    def resolve_access(self, workspace_id: str, user: User) -> ManagementAccess:
        workspace = self._require_workspace(workspace_id)
        is_owner = workspace.owner_id == user.id
        is_interno_adm = bool(user.interno_adm)
        level: ManagementLevel = "none"
        if is_owner or is_interno_adm:
            level = "grant"
        else:
            grant = self._repo.get_active_grant(workspace_id, user.id)
            if grant and grant.level in LEVEL_RANK:
                level = grant.level  # type: ignore[assignment]
        return ManagementAccess(
            workspace=workspace,
            user=user,
            level=level,
            is_owner=is_owner,
            is_interno_adm=is_interno_adm,
            permission_version=int(getattr(workspace, "management_permission_version", 1) or 1),
        )

    def build_capabilities(self, access: ManagementAccess) -> ManagementCapabilities:
        r, m, g = access.can_read, access.can_modify, access.can_grant
        is_owner_or_internal = access.is_owner or access.is_interno_adm
        return ManagementCapabilities(
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
        )

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

    def require_read(self, workspace_id: str, user: User) -> ManagementAccess:
        access = self.resolve_access(workspace_id, user)
        if not access.can_read:
            raise self._forbidden("Você não tem permissão de leitura na gestão deste workspace.", required="management.read")
        return access

    def require_modify(self, workspace_id: str, user: User) -> ManagementAccess:
        access = self.resolve_access(workspace_id, user)
        if not access.can_modify:
            raise self._forbidden("Você não tem permissão de modificação na gestão deste workspace.", required="management.modify")
        return access

    def require_grant(self, workspace_id: str, user: User) -> ManagementAccess:
        access = self.resolve_access(workspace_id, user)
        if not access.can_grant:
            raise self._forbidden("Você não tem permissão para gerenciar grants da gestão.", required="management.grant")
        return access

    def list_grants(self, workspace_id: str, actor: User) -> list[WorkspaceManagementGrant]:
        self.require_read(workspace_id, actor)
        return self._repo.list_active_grants(workspace_id)

    def create_or_update_grant(self, workspace_id: str, actor: User, *, target_user_id: str, level: str, reason: str | None = None, request_id: str | None = None) -> WorkspaceManagementGrant:
        access = self.require_grant(workspace_id, actor)
        workspace = access.workspace
        if level not in ("read", "modify", "grant"):
            raise self._conflict("Nível de grant inválido", "MANAGEMENT_GRANT_INVALID_LEVEL")
        # R9: only owner/interno_adm can grant 'grant'
        if level == "grant" and not (access.is_owner or access.is_interno_adm):
            raise self._forbidden(
                "Apenas owner ou interno_adm podem conceder nível grant.",
                error_code="MANAGEMENT_GRANT_ESCALATION_DENIED",
                required="management.grant.grant",
            )
        # target must be workspace member? plan says "qualquer usuário do workspace" - we'll require they exist as user? at least check not self weird cases; better require workspace member
        if not self._is_member_operational(workspace, User(id=target_user_id, email="", senha_hash="", cpf="", idade=0, termos_contrato=True, interno_adm=False, status_ativo=True)) and self._repo.get_workspace_member(workspace_id, target_user_id) is None:
            # owner is operational; for target, just check membership by repo
            pass
        target_member = self._repo.get_workspace_member(workspace_id, target_user_id)
        if workspace.owner_id != target_user_id and target_member is None:
            raise self._not_found("Usuário alvo não é membro do workspace", "WORKSPACE_MEMBER_NOT_FOUND")

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
            )
            self._repo.commit()
            return grant
        except Exception:
            self._repo.rollback()
            raise

    def revoke_grant(self, workspace_id: str, actor: User, *, target_user_id: str, reason: str | None = None, request_id: str | None = None) -> None:
        access = self.require_grant(workspace_id, actor)
        workspace = access.workspace
        break_glass = self._ensure_break_glass(workspace, actor, reason, "management.grant.revoke")
        grant = self._repo.get_active_grant(workspace_id, target_user_id)
        if not grant:
            raise self._not_found("Grant de gestão não encontrado", "MANAGEMENT_GRANT_NOT_FOUND")
        # R9: revoking grant-level grant requires owner/interno_adm
        if grant.level == "grant" and not (access.is_owner or access.is_interno_adm):
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
            )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
