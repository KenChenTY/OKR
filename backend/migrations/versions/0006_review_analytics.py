"""KR benefits, quarterly retrospective plans and strategic assessments."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import DATETIME2

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    # Historical benefits remain unassigned; never infer a KR for existing records.
    op.add_column("benefits", sa.Column("kr_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_benefits_kr", "benefits", "key_results", ["kr_id"], ["id"])
    op.create_index("ix_benefits_kr_id", "benefits", ["kr_id"])
    op.create_table(
        "quarterly_reviews",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("objective_id", sa.BigInteger(), sa.ForeignKey("objectives.id"), nullable=False, unique=True),
        sa.Column("reviewer_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Unicode(20), nullable=False),
        sa.Column("summary", sa.UnicodeText(), nullable=False),
        sa.Column("lessons", sa.UnicodeText(), nullable=False),
        sa.Column("next_steps", sa.UnicodeText(), nullable=False),
        sa.Column("completed_at", DATETIME2(3), nullable=True),
        sa.CheckConstraint("status IN ('Pending','Completed')"),
    )
    op.create_table(
        "strategic_assessments",
        sa.Column("objective_id", sa.BigInteger(), sa.ForeignKey("objectives.id"), primary_key=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.UnicodeText(), nullable=False),
        sa.Column("assessed_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assessed_at", DATETIME2(3), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 100"),
    )


def downgrade():
    raise RuntimeError("Review history must not be removed by downgrade")
