from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from app.common.email import build_invite_url, send_invitation_email
from app.common.exceptions import ConflictException
from app.config.settings import Settings, get_settings
from app.modules.organization.dataproviders.repository import OrganizationRepository
from app.modules.organization.domain.models import Invitation, OrganizationMember
from app.modules.organization.schemas.dto import (
    InvitationAcceptResponse,
    InvitationCreateRequest,
    InvitationCreateResponse,
    InvitationResponse,
)
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from common.errors import ExceptionData, ForbiddenException, NotFoundException

_INVITATION_MANAGE_ROLES = frozenset({"owner", "admin"})


class InvitationService:
    def __init__(self, repo: OrganizationRepository, settings: Settings | None = None) -> None:
        self._repo = repo
        self._settings = settings or get_settings()

    @staticmethod
    def _not_found(message: str, error_code: str) -> NotFoundException:
        return NotFoundException(
            ExceptionData(message=message, error_code=error_code, error_layer="organization"),
            is_expected=True,
        )

    @staticmethod
    def _forbidden(
        message: str, *, required: str, error_code: str = "FORBIDDEN"
    ) -> ForbiddenException:
        return ForbiddenException(
            ExceptionData(
                message=message,
                error_code=error_code,
                error_layer="organization",
                required_capability=required,
            ),
            is_expected=True,
        )

    @staticmethod
    def _conflict(message: str, error_code: str) -> ConflictException:
        return ConflictException(
            ExceptionData(message=message, error_code=error_code, error_layer="organization"),
            is_expected=True,
        )

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _status(
        invitation: Invitation, *, now: datetime
    ) -> Literal["pending", "accepted", "revoked", "expired"]:
        if invitation.accepted_at is not None:
            return "accepted"
        if invitation.revoked_at is not None:
            return "revoked"
        expires_at = invitation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            return "expired"
        return "pending"

    def _require_organization(self, organization_id: str):
        organization = self._repo.get_by_id(organization_id)
        if organization is None:
            raise self._not_found("Organização não encontrada", "ORGANIZATION_NOT_FOUND")
        return organization

    def _authorize_manage(
        self, organization_id: str, actor: User, *, reason: str | None = None
    ) -> str:
        role = self._repo.get_organization_role(organization_id, actor.id)
        if role in _INVITATION_MANAGE_ROLES:
            return role
        if actor.interno_adm:
            if role is not None:
                return "interno_adm"
            if not (reason and reason.strip()):
                raise self._forbidden(
                    "Ação de interno_adm fora da organização exige justificativa (break-glass).",
                    required="organization.break_glass_reason",
                    error_code="BREAK_GLASS_REASON_REQUIRED",
                )
            return "interno_adm"
        # 404/403 indistinguível para não enumerar quando não tem acesso.
        raise self._not_found("Organização não encontrada", "ORGANIZATION_NOT_FOUND")

    def _require_workspace_in_org(self, organization_id: str, workspace_id: str) -> Workspace:
        workspace = self._repo.get_workspace(workspace_id)
        if workspace is None or workspace.organization_id != organization_id:
            raise self._not_found("Workspace não encontrado", "WORKSPACE_NOT_FOUND")
        return workspace

    def _check_seat_limit(self, organization_id: str, *, extra_users: int = 0) -> None:
        limit, plan_name = self._repo.get_seat_limit(organization_id)
        if limit is None:
            return
        seats_used = self._repo.count_seats_used(organization_id)
        projected = seats_used + max(extra_users, 0)
        if projected > limit:
            raise self._conflict(
                f"O plano {plan_name} permite {limit} seats; {seats_used} de {limit} estão em uso.",
                "SEAT_LIMIT_EXCEEDED",
            )

    def create_invitation(
        self,
        organization_id: str,
        actor: User,
        payload: InvitationCreateRequest,
        *,
        reason: str | None = None,
    ) -> InvitationCreateResponse:
        self._authorize_manage(organization_id, actor, reason=reason)
        self._require_organization(organization_id)
        self._require_workspace_in_org(organization_id, payload.workspace_id)
        email = self._normalize_email(str(payload.email))

        now = datetime.now(UTC)
        pending = self._repo.get_pending_invitation(
            organization_id=organization_id, workspace_id=payload.workspace_id, email=email
        )
        if pending is not None and self._status(pending, now=now) == "pending":
            raise self._conflict(
                "Já existe convite pendente para este e-mail",
                "INVITATION_ALREADY_EXISTS",
            )

        # Seat limit: convite pode adicionar uma nova pessoa; bloqueia conservadoramente.
        self._check_seat_limit(organization_id, extra_users=1)

        token = secrets.token_urlsafe(32)
        invitation = Invitation(
            organization_id=organization_id,
            workspace_id=payload.workspace_id,
            email=email,
            role=payload.role,
            token_hash=self._hash_token(token),
            expires_at=now + timedelta(days=payload.expires_in_days),
            invited_by_id=actor.id,
        )
        try:
            self._repo.add_invitation(invitation)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise

        workspace = self._repo.get_workspace(payload.workspace_id)
        organization = self._repo.get_by_id(organization_id)
        invite_url = build_invite_url(self._settings.frontend_base_url, token)
        email_sent = send_invitation_email(
            settings=self._settings,
            to_email=invitation.email,
            invite_url=invite_url,
            workspace_name=workspace.name if workspace else None,
            organization_name=organization.name if organization else None,
        )

        return InvitationCreateResponse(
            id=invitation.id,
            organization_id=invitation.organization_id,
            workspace_id=invitation.workspace_id,
            email=invitation.email,
            role=invitation.role,  # type: ignore[arg-type]
            status="pending",
            expires_at=invitation.expires_at,
            invited_by_id=invitation.invited_by_id,
            criado_em=invitation.criado_em,
            token=token,
            invite_url=invite_url,
            email_sent=email_sent,
        )

    def list_invitations(
        self, organization_id: str, actor: User, *, reason: str | None = None
    ) -> list[InvitationResponse]:
        self._authorize_manage(organization_id, actor, reason=reason)
        self._require_organization(organization_id)
        now = datetime.now(UTC)
        invitations = self._repo.list_invitations(organization_id)
        return [
            InvitationResponse(
                id=inv.id,
                organization_id=inv.organization_id,
                workspace_id=inv.workspace_id,
                email=inv.email,
                role=inv.role,
                status=self._status(inv, now=now),
                expires_at=inv.expires_at,
                accepted_at=inv.accepted_at,
                revoked_at=inv.revoked_at,
                invited_by_id=inv.invited_by_id,
                criado_em=inv.criado_em,
            )
            for inv in invitations
        ]

    def revoke_invitation(
        self,
        organization_id: str,
        invitation_id: str,
        actor: User,
        *,
        reason: str | None = None,
    ) -> InvitationResponse:
        self._authorize_manage(organization_id, actor, reason=reason)
        self._require_organization(organization_id)
        invitation = self._repo.get_invitation_by_id(invitation_id)
        if invitation is None or invitation.organization_id != organization_id:
            raise self._not_found("Convite não encontrado", "INVITATION_NOT_FOUND")
        now = datetime.now(UTC)
        status = self._status(invitation, now=now)
        if status == "accepted":
            raise self._conflict("Convite já aceito", "INVITATION_ALREADY_USED")
        if status == "revoked":
            raise self._conflict("Convite já revogado", "INVITATION_REVOKED")
        if status == "expired":
            raise self._conflict("Convite expirado", "INVITATION_EXPIRED")
        try:
            self._repo.mark_invitation_revoked(invitation, revoked_at=now)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return InvitationResponse(
            id=invitation.id,
            organization_id=invitation.organization_id,
            workspace_id=invitation.workspace_id,
            email=invitation.email,
            role=invitation.role,
            status="revoked",
            expires_at=invitation.expires_at,
            accepted_at=invitation.accepted_at,
            revoked_at=invitation.revoked_at,
            invited_by_id=invitation.invited_by_id,
            criado_em=invitation.criado_em,
        )

    def accept_invitation(self, token: str, actor: User) -> InvitationAcceptResponse:
        invitation = self._repo.get_invitation_by_token_hash(self._hash_token(token))
        if invitation is None:
            raise self._not_found("Convite não encontrado", "INVITATION_NOT_FOUND")
        now = datetime.now(UTC)
        status = self._status(invitation, now=now)
        if status == "accepted":
            raise self._conflict("Convite já aceito", "INVITATION_ALREADY_USED")
        if status == "revoked":
            raise self._conflict("Convite revogado", "INVITATION_REVOKED")
        if status == "expired":
            raise self._conflict("Convite expirado", "INVITATION_EXPIRED")

        if self._normalize_email(actor.email) != self._normalize_email(invitation.email):
            raise self._forbidden(
                "O e-mail autenticado não corresponde ao convite.",
                required="invitation.email_match",
                error_code="INVITATION_EMAIL_MISMATCH",
            )

        self._require_organization(invitation.organization_id)
        self._require_workspace_in_org(invitation.organization_id, invitation.workspace_id)

        # Revalidate seat limit at accept time. Only count if user not already counted.
        already_counted = self._repo.is_user_counted_in_seats(invitation.organization_id, actor.id)
        self._check_seat_limit(invitation.organization_id, extra_users=0 if already_counted else 1)

        org_member = self._repo.get_member(invitation.organization_id, actor.id)
        ws_member = self._repo.get_workspace_member(invitation.workspace_id, actor.id)
        created_org = False
        created_ws = False
        try:
            if org_member is None:
                org_role = "admin" if invitation.role == "admin" else "member"
                self._repo.add_member(
                    OrganizationMember(
                        organization_id=invitation.organization_id,
                        user_id=actor.id,
                        role=org_role,
                        status="active",
                    )
                )
                created_org = True
            if ws_member is None:
                ws_role = "admin" if invitation.role == "admin" else "member"
                self._repo.add_workspace_member(
                    WorkspaceMember(
                        workspace_id=invitation.workspace_id,
                        user_id=actor.id,
                        role=ws_role,
                    )
                )
                created_ws = True
            self._repo.mark_invitation_accepted(invitation, accepted_at=now)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise

        return InvitationAcceptResponse(
            id=invitation.id,
            organization_id=invitation.organization_id,
            workspace_id=invitation.workspace_id,
            email=invitation.email,
            role=invitation.role,
            accepted_at=now,
            organization_member_created=created_org,
            workspace_member_created=created_ws,
        )
