"""create kanban cards and related tables

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cards",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "board_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("boards.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "column_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("board_columns.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("team_id", sa.Uuid(as_uuid=False), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", sa.String(50), nullable=True),
        sa.Column("priority", sa.String(50), nullable=True),
        sa.Column("assignee_id", sa.Uuid(as_uuid=False), nullable=True, index=True),
        sa.Column("reporter_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("fix_version", sa.String(100), nullable=True),
        sa.Column("budget_project", sa.String(200), nullable=True),
        sa.Column("parent_id", sa.Uuid(as_uuid=False), nullable=True, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status_ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "card_subtasks",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "card_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("cards.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("key", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="todo"),
        sa.Column("priority", sa.String(50), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("assignee_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "card_checklist",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "card_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("cards.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "card_comments",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "card_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("cards.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("author_id", sa.Uuid(as_uuid=False), nullable=False, index=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "card_history",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "card_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("cards.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("author_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "card_worklogs",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "card_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("cards.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("author_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("time_spent_minutes", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "card_links",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "card_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("cards.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "card_watchers",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "card_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("cards.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False, index=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "card_custom_fields",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "card_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("cards.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("field_key", sa.String(100), nullable=False),
        sa.Column("field_value", sa.Text(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("card_custom_fields")
    op.drop_table("card_watchers")
    op.drop_table("card_links")
    op.drop_table("card_worklogs")
    op.drop_table("card_history")
    op.drop_table("card_comments")
    op.drop_table("card_checklist")
    op.drop_table("card_subtasks")
    op.drop_table("cards")
