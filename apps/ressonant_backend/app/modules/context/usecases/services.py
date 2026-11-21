from app.modules.context.dataproviders.repository import ContextRepository
from app.modules.context.schemas.dto import (
    BillingCapabilities,
    ContextCapabilities,
    DomainCapabilities,
    MeContextResponse,
    OrganizationContextResponse,
    SubscriptionContextResponse,
    TeamContextResponse,
    WorkspaceContextResponse,
)
from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.user.domain.models import User
from app.modules.user.schemas import UserResponse
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.workspace_management.schemas.dto import ManagementCapabilities
from app.modules.workspace_management.usecases.services import WorkspaceManagementService

_MANAGEMENT_CAPABILITY_FIELDS = (
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
)
_BILLING_MANAGE_ROLES = frozenset({"owner", "billing_owner"})


class ContextService:
    """Monta o bootstrap apenas com fatos persistidos e capacidades do RWMS."""

    def __init__(self, repo: ContextRepository, management: WorkspaceManagementService) -> None:
        self._repo = repo
        self._management = management

    def get_context(self, user: User) -> MeContextResponse:
        workspace_rows = self._repo.list_workspaces_for_user(user.id)
        workspaces = [
            self._build_workspace(workspace, member, user) for workspace, member in workspace_rows
        ]
        organizations = self._build_organizations(user.id, workspace_rows)
        active_organization = next(
            (organization for organization in organizations if organization.status == "active"),
            None,
        )

        return MeContextResponse(
            user=UserResponse.model_validate(user),
            organizations=organizations,
            active_organization=active_organization,
            workspaces=workspaces,
            capabilities=ContextCapabilities(
                management=self._merge_capabilities(
                    [workspace.capabilities for workspace in workspaces]
                ),
                billing=BillingCapabilities(
                    view=active_organization is not None,
                    manage=(
                        active_organization.role in _BILLING_MANAGE_ROLES
                        if active_organization is not None
                        else False
                    ),
                ),
                domain=DomainCapabilities(
                    cards_write=bool(workspaces) or self._repo.has_team_membership(user.id)
                ),
            ),
            subscription=self._build_subscription(active_organization),
            permission_version=max(
                (workspace.permission_version for workspace in workspaces), default=1
            ),
        )

    def _build_organizations(
        self, user_id: str, workspace_rows: list[tuple[Workspace, WorkspaceMember]]
    ) -> list[OrganizationContextResponse]:
        memberships = self._repo.list_organization_memberships(user_id)
        organizations: dict[str, tuple[Organization, OrganizationMember | None]] = {
            organization.id: (organization, member) for organization, member in memberships
        }
        missing_ids = {
            workspace.organization_id
            for workspace, _ in workspace_rows
            if workspace.organization_id not in organizations
        }
        organizations.update(
            (organization_id, (organization, None))
            for organization_id, organization in self._repo.list_organizations_by_ids(
                missing_ids
            ).items()
        )

        return [
            OrganizationContextResponse(
                id=organization.id,
                name=organization.name,
                slug=organization.slug,
                role=member.role if member is not None else "member",
                status=member.status if member is not None else "active",
            )
            for organization, member in organizations.values()
        ]

    def _build_workspace(
        self, workspace: Workspace, member: WorkspaceMember, user: User
    ) -> WorkspaceContextResponse:
        access = self._management.resolve_access(workspace.id, user)
        return WorkspaceContextResponse(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            organization_id=workspace.organization_id,
            role=member.role,
            member_ids=[
                workspace_member.user_id
                for workspace_member in self._repo.list_workspace_members(workspace.id)
            ],
            teams=self._build_teams(workspace, user),
            capabilities=self._management.build_capabilities(access),
            permission_version=int(workspace.management_permission_version or 1),
        )

    def _build_teams(self, workspace: Workspace, user: User) -> list[TeamContextResponse]:
        return [
            TeamContextResponse(
                id=team.id,
                name=team.name,
                slug=team.slug,
                key_prefix=team.key_prefix,
                role=member.role,
            )
            for team, member in self._repo.list_user_teams(workspace.id, user.id)
        ]

    @staticmethod
    def _merge_capabilities(items: list[ManagementCapabilities]) -> ManagementCapabilities:
        return ManagementCapabilities(
            **{
                field: any(getattr(capabilities, field) for capabilities in items)
                for field in _MANAGEMENT_CAPABILITY_FIELDS
            }
        )

    def _build_subscription(
        self, active_organization: OrganizationContextResponse | None
    ) -> SubscriptionContextResponse | None:
        if active_organization is None:
            return None
        row = self._repo.get_active_subscription(active_organization.id)
        if row is None:
            return None
        subscription, plan = row
        return SubscriptionContextResponse(
            plan_code=plan.code,
            plan_name=plan.name,
            status=subscription.status,
            seats_purchased=subscription.seats_purchased,
            seat_limit=plan.seat_limit,
            trial_ends_at=subscription.trial_ends_at,
            current_period_end=subscription.current_period_end,
            price_cents=plan.price_cents,
            overage_cents_per_seat=plan.overage_cents_per_seat,
        )
