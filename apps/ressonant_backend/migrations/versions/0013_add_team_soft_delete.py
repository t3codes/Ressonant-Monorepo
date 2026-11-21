"""add team soft delete fields

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teams", sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("teams", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("teams", sa.Column("deleted_by", sa.Uuid(as_uuid=False), nullable=True))
    op.create_index("ix_teams_is_deleted", "teams", ["is_deleted"])


def downgrade() -> None:
    op.drop_index("ix_teams_is_deleted", table_name="teams")
    op.drop_column("teams", "deleted_by")
    op.drop_column("teams", "deleted_at")
    op.drop_column("teams", "is_deleted")
