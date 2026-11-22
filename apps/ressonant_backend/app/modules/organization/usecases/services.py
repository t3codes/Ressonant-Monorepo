from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from app.common.email import build_invite_url
from app.common.email_outbox import enqueue_email
from app.common.exceptions import ConflictException
from app.config.settings import Settings, get_settings
from app.modules.chat.dataproviders.repository import ChannelRepository
from app.modules.organization.dataproviders.repository import OrganizationRepository
from app.modules.organization.domain.models import Invitation, OrganizationMember
from app.modules.organization.schemas.dto import (
    InvitationAcceptResponse,
    InvitationCreateRequest,
    InvitationCreateResponse,
    InvitationPublicResponse,
    InvitationResendResponse,
    InvitationResponse,
)
from app.modules.teams.dataproviders.repository import TeamRepository
from app.modules.teams.domain.models import TeamMember
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.workspace_management.domain.models import AuditEvent
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
    def _mask_email(email: str) -> str:
        local, _, domain = email.partition("@")
        if not domain:
            return "***"
        head = local[:1]
        tail = local[-1:] if len(local) > 2 else ""
        return f"{head}***{tail}@{domain}"

    @staticmethod
    def _status(
        invitation: Invitation, *, now: datetime
    ) -> Literal["pending", "accepted", "revoked", "expired", "declined"]:
        if invitation.accepted_at is not None:
            return "accepted"
        if invitation.revoked_at is not None:
            return "revoked"
        if getattr(invitation, "declined_at", None) is not None:
            return "declined"
        expires_at = invitation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            return "expired"
        return "pending"

    def _audit(
        self,
        *,
        organization_id: str | None,
        action: str,
        actor: User | None,
        actor_type: str,
        invitation: Invitation,
        result: str = "success",
        before: dict | None = None,
        after: dict | None = None,
    ) -> None:
        self._repo.add_audit_event(
            AuditEvent(
                organization_id=organization_id or invitation.organization_id,
                workspace_id=invitation.workspace_id,
                scope="organization",
                actor_user_id=actor.id if actor else None,
                actor_type=actor_type,
                actor_role=getattr(actor, "role", None),
                action=action,
                entity_type="invitation",
                entity_id=invitation.id,
                result=result,
                before=before,
                after=after,
                metadata_={"email": invitation.email, "role": invitation.role},
            )
        )

    def _secret_response_fields(self, *, token: str, invite_url: str) -> dict[str, str | None]:
        if self._settings.environment == "development":
            return {"token": token, "invite_url": invite_url}
        return {"token": None, "invite_url": None}

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

    def _ensure_default_team_membership(self, *, workspace_id: str, user_id: str, role: str) -> bool:
        team_repo = TeamRepository(self._repo.db)
        team = team_repo.get_default_for_workspace(workspace_id)
        if team is None:
            return False
        if team_repo.is_member(team.id, user_id) is not None:
            return False
        team_role = "admin" if role == "admin" else "member"
        self._repo.db.add(TeamMember(team_id=team.id, user_id=user_id, role=team_role))
        self._repo.db.flush()
        return True

    def _ensure_default_channel_membership(self, *, workspace_id: str, user_id: str) -> bool:
        channel_repo = ChannelRepository(self._repo.db)
        channel = channel_repo.get_default_for_workspace(workspace_id)
        if channel is None:
            return False
        try:
            members = json.loads(channel.member_ids or "[]")
            if not isinstance(members, list):
                members = []
        except Exception:
            members = []
        members = [m for m in members if isinstance(m, str)]
        if user_id in members:
            return False
        members.append(user_id)
        channel.member_ids = json.dumps(members)
        self._repo.db.add(channel)
        self._repo.db.flush()
        return True

    def _enqueue_invite_email(
        self, *, invitation: Invitation, token: str, event_type: str, actor: User | None
    ) -> tuple[str, bool]:
        workspace = self._repo.get_workspace(invitation.workspace_id)
        organization = self._repo.get_by_id(invitation.organization_id)
        invite_url = build_invite_url(self._settings.frontend_base_url, token)

        if not self._settings.email_enabled or not self._settings.smtp_host:
            self._repo.set_invitation_send_status(invitation, send_status="not_configured")
            self._audit(
                organization_id=invitation.organization_id,
                action="invitation.email_skipped",
                actor=actor,
                actor_type="user" if actor else "system",
                invitation=invitation,
                result="skipped",
                after={"send_status": "not_configured", "reason": "email_disabled"},
            )
            self._repo.commit()
            return invite_url, False

        payload = {
            "invite_url": invite_url,
            "workspace_name": workspace.name if workspace else None,
            "organization_name": organization.name if organization else None,
            "inviter_name": actor.name
            if actor and actor.name
            else (actor.email if actor else None),
            "role": invitation.role,
            "expires_at": invitation.expires_at.isoformat(),
            "invitation_id": invitation.id,
        }
        dedupe_key = f"{event_type}:{invitation.id}:{self._hash_token(token)}"
        row = enqueue_email(
            self._repo.db,
            event_type=event_type,
            recipient_email=invitation.email,
            subject="Convite para o Ressonant",
            payload=payload,
            dedupe_key=dedupe_key,
        )
        # if an identical dedupe row already exists and was sent/skipped, reflect it
        if row.status == "sent":
            self._repo.set_invitation_send_status(
                invitation, send_status="sent", last_sent_at=row.sent_at
            )
        elif row.status == "skipped":
            self._repo.set_invitation_send_status(invitation, send_status="not_configured")
        else:
            self._repo.set_invitation_send_status(invitation, send_status="pending")
        self._repo.commit()
        refreshed = self._repo.get_invitation_by_id(invitation.id) or invitation
        return invite_url, refreshed.send_status == "sent"

    def create_invitation(
        self,
        organization_id: str,
        actor: User,
        payload: InvitationCreateRequest,
        *,
        reason: str | None = None,
    ) -> InvitationCreateResponse:
        self._authorize_manage(organization_id, actor, reason=reason)
        org = self._repo.lock_organization(organization_id)
        if org is None:
            raise self._not_found("Organização não encontrada", "ORGANIZATION_NOT_FOUND")
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
            send_status="pending",
        )
        try:
            self._repo.add_invitation(invitation)
            self._audit(
                organization_id=organization_id,
                action="invitation.created",
                actor=actor,
                actor_type="user",
                invitation=invitation,
                after={"status": "pending", "expires_at": invitation.expires_at.isoformat()},
            )
            self._repo.commit()
        except Exception as exc:
            self._repo.rollback()
            from sqlalchemy.exc import IntegrityError

            if isinstance(exc, IntegrityError):
                raise self._conflict(
                    "Já existe convite pendente para este e-mail",
                    "INVITATION_ALREADY_EXISTS",
                ) from None
            raise

        invite_url, email_sent = self._enqueue_invite_email(
            invitation=invitation, token=token, event_type="invitation.created", actor=actor
        )
        secret_fields = self._secret_response_fields(token=token, invite_url=invite_url)

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
            token=secret_fields["token"],
            invite_url=secret_fields["invite_url"],
            email_sent=email_sent,
        )

    def list_invitations(
        self, organization_id: str, actor: User, *, reason: str | None = None
    ) -> list[InvitationResponse]:
        self._authorize_manage(organization_id, actor, reason=reason)
        self._require_organization(organization_id)
        now = datetime.now(UTC)
        invitations = self._repo.list_invitations(organization_id)
        return [self._to_response(inv, now=now) for inv in invitations]

    def _to_response(self, inv: Invitation, *, now: datetime) -> InvitationResponse:
        return InvitationResponse(
            id=inv.id,
            organization_id=inv.organization_id,
            workspace_id=inv.workspace_id,
            email=inv.email,
            role=inv.role,
            status=self._status(inv, now=now),
            expires_at=inv.expires_at,
            accepted_at=inv.accepted_at,
            revoked_at=inv.revoked_at,
            declined_at=getattr(inv, "declined_at", None),
            resent_at=getattr(inv, "resent_at", None),
            last_sent_at=getattr(inv, "last_sent_at", None),
            send_status=getattr(inv, "send_status", None),
            invited_by_id=inv.invited_by_id,
            criado_em=inv.criado_em,
        )

    def get_public_invitation(self, token: str) -> InvitationPublicResponse:
        invitation = self._repo.get_invitation_by_token_hash(self._hash_token(token))
        if invitation is None:
            raise self._not_found("Convite não encontrado", "INVITATION_NOT_FOUND")
        now = datetime.now(UTC)
        status = self._status(invitation, now=now)
        org = self._repo.get_by_id(invitation.organization_id)
        ws = self._repo.get_workspace(invitation.workspace_id)
        inviter = (
            self._repo.get_user_by_id(invitation.invited_by_id)
            if hasattr(self._repo, "get_user_by_id")
            else None
        )
        user_exists = bool(self._repo.get_user_by_email(invitation.email))
        return InvitationPublicResponse(
            organization_name=org.name if org else "Organização",
            workspace_name=ws.name if ws else "Workspace",
            role=invitation.role,
            email_masked=self._mask_email(invitation.email),
            expires_at=invitation.expires_at,
            status=status,
            invited_by_name=(inviter.name or inviter.email) if inviter else None,
            user_exists=user_exists,
        )

    def resend_invitation(
        self, organization_id: str, invitation_id: str, actor: User, *, reason: str | None = None
    ) -> InvitationResendResponse:
        self._authorize_manage(organization_id, actor, reason=reason)
        try:
            invitation = self._repo.get_invitation_by_id(invitation_id, for_update=True)
            if invitation is None or invitation.organization_id != organization_id:
                raise self._not_found("Convite não encontrado", "INVITATION_NOT_FOUND")
            now = datetime.now(UTC)
            status = self._status(invitation, now=now)
            if status != "pending":
                raise self._conflict(
                    "Apenas convites pendentes podem ser reenviados", "INVITATION_NOT_RESENDABLE"
                )
            token = secrets.token_urlsafe(32)
            before = {"expires_at": invitation.expires_at.isoformat()}
            self._repo.update_invitation_for_resend(
                invitation,
                token_hash=self._hash_token(token),
                expires_at=now + timedelta(days=7),
                resent_at=now,
            )
            self._audit(
                organization_id=organization_id,
                action="invitation.resent",
                actor=actor,
                actor_type="user",
                invitation=invitation,
                before=before,
                after={"expires_at": invitation.expires_at.isoformat()},
            )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        invite_url, email_sent = self._enqueue_invite_email(
            invitation=invitation, token=token, event_type="invitation.resent", actor=actor
        )
        refreshed = self._repo.get_invitation_by_id(invitation.id) or invitation
        base = self._to_response(refreshed, now=datetime.now(UTC))
        secret_fields = self._secret_response_fields(token=token, invite_url=invite_url)
        return InvitationResendResponse(
            **base.model_dump(),
            token=secret_fields["token"],
            invite_url=secret_fields["invite_url"],
            email_sent=email_sent,
        )

    def revoke_invitation(
        self,
        organization_id: str,
        invitation_id: str,
        actor: User,
        *,
        reason: str | None = None,
    ) -> InvitationResponse:
        """Compatibilidade: revoga convite pendente. Preferir delete para limpar histórico."""
        self._authorize_manage(organization_id, actor, reason=reason)
        try:
            invitation = self._repo.get_invitation_by_id(invitation_id, for_update=True)
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
            if status == "declined":
                raise self._conflict("Convite já recusado", "INVITATION_DECLINED")
            self._repo.mark_invitation_revoked(invitation, revoked_at=now)
            self._audit(
                organization_id=organization_id,
                action="invitation.revoked",
                actor=actor,
                actor_type="user",
                invitation=invitation,
            )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return self._to_response(invitation, now=now)

    def delete_invitation(
        self,
        organization_id: str,
        invitation_id: str,
        actor: User,
        *,
        reason: str | None = None,
    ) -> None:
        self._authorize_manage(organization_id, actor, reason=reason)
        try:
            invitation = self._repo.get_invitation_by_id(invitation_id, for_update=True)
            if invitation is None or invitation.organization_id != organization_id:
                raise self._not_found("Convite não encontrado", "INVITATION_NOT_FOUND")
            self._audit(
                organization_id=organization_id,
                action="invitation.deleted",
                actor=actor,
                actor_type="user",
                invitation=invitation,
                before={"status": self._status(invitation, now=datetime.now(UTC))},
                after={"deleted": True},
            )
            self._repo.delete_invitation(invitation)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise

    def accept_invitation(self, token: str, actor: User) -> InvitationAcceptResponse:
        token_hash = self._hash_token(token)
        try:
            invitation = self._repo.get_invitation_by_token_hash(token_hash, for_update=True)
            if invitation is None:
                raise self._not_found("Convite não encontrado", "INVITATION_NOT_FOUND")
            now = datetime.now(UTC)
            status = self._status(invitation, now=now)
            if status == "accepted":
                if self._normalize_email(actor.email) == self._normalize_email(invitation.email):
                    org_member = self._repo.get_member(invitation.organization_id, actor.id)
                    ws_member = self._repo.get_workspace_member(invitation.workspace_id, actor.id)
                    if org_member is not None and ws_member is not None:
                        team_member_created = self._ensure_default_team_membership(
                            workspace_id=invitation.workspace_id, user_id=actor.id, role=invitation.role
                        )
                        channel_member_added = self._ensure_default_channel_membership(
                            workspace_id=invitation.workspace_id, user_id=actor.id
                        )
                        if team_member_created or channel_member_added:
                            self._audit(
                                organization_id=invitation.organization_id,
                                action="invitation.accepted.memberships_repaired",
                                actor=actor,
                                actor_type="user",
                                invitation=invitation,
                                after={
                                    "organization_member_created": False,
                                    "workspace_member_created": False,
                                    "team_member_created": team_member_created,
                                    "channel_member_added": channel_member_added,
                                },
                            )
                            self._repo.commit()
                        return InvitationAcceptResponse(
                            id=invitation.id,
                            organization_id=invitation.organization_id,
                            workspace_id=invitation.workspace_id,
                            email=invitation.email,
                            role=invitation.role,
                            accepted_at=invitation.accepted_at or now,
                            organization_member_created=False,
                            workspace_member_created=False,
                        )
                raise self._conflict("Convite já aceito", "INVITATION_ALREADY_USED")
            if status == "revoked":
                raise self._conflict("Convite revogado", "INVITATION_REVOKED")
            if status == "expired":
                raise self._conflict("Convite expirado", "INVITATION_EXPIRED")
            if status == "declined":
                raise self._conflict("Convite recusado", "INVITATION_DECLINED")

            if self._normalize_email(actor.email) != self._normalize_email(invitation.email):
                raise self._forbidden(
                    "O e-mail autenticado não corresponde ao convite.",
                    required="invitation.email_match",
                    error_code="INVITATION_EMAIL_MISMATCH",
                )

            org = self._repo.lock_organization(invitation.organization_id)
            if org is None:
                raise self._not_found("Organização não encontrada", "ORGANIZATION_NOT_FOUND")
            self._require_workspace_in_org(invitation.organization_id, invitation.workspace_id)

            already_counted = self._repo.is_user_counted_in_seats(
                invitation.organization_id, actor.id
            )
            self._check_seat_limit(
                invitation.organization_id, extra_users=0 if already_counted else 1
            )

            org_member = self._repo.get_member(invitation.organization_id, actor.id)
            ws_member = self._repo.get_workspace_member(invitation.workspace_id, actor.id)
            created_org = False
            created_ws = False
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
            team_member_created = self._ensure_default_team_membership(
                workspace_id=invitation.workspace_id, user_id=actor.id, role=invitation.role
            )
            channel_member_added = self._ensure_default_channel_membership(
                workspace_id=invitation.workspace_id, user_id=actor.id
            )
            self._repo.mark_invitation_accepted(invitation, accepted_at=now)
            self._audit(
                organization_id=invitation.organization_id,
                action="invitation.accepted",
                actor=actor,
                actor_type="user",
                invitation=invitation,
                after={
                    "organization_member_created": created_org,
                    "workspace_member_created": created_ws,
                    "team_member_created": team_member_created,
                    "channel_member_added": channel_member_added,
                },
            )
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

    def decline_invitation(self, token: str) -> InvitationResponse:
        token_hash = self._hash_token(token)
        try:
            invitation = self._repo.get_invitation_by_token_hash(token_hash, for_update=True)
            if invitation is None:
                raise self._not_found("Convite não encontrado", "INVITATION_NOT_FOUND")
            now = datetime.now(UTC)
            status = self._status(invitation, now=now)
            if status == "declined":
                return self._to_response(invitation, now=now)
            if status != "pending":
                if status == "accepted":
                    raise self._conflict("Convite já aceito", "INVITATION_ALREADY_USED")
                if status == "revoked":
                    raise self._conflict("Convite revogado", "INVITATION_REVOKED")
                if status == "expired":
                    raise self._conflict("Convite expirado", "INVITATION_EXPIRED")
            self._repo.mark_invitation_declined(invitation, declined_at=now)
            self._audit(
                organization_id=invitation.organization_id,
                action="invitation.declined",
                actor=None,
                actor_type="anonymous",
                invitation=invitation,
            )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return self._to_response(invitation, now=datetime.now(UTC))
