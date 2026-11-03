"""Restrict sensitive objectives and record KR evidence source."""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("objectives", sa.Column("visibility", sa.Unicode(20), server_default=sa.text("N'organization'"), nullable=False))
    op.create_check_constraint("ck_objective_visibility", "objectives", "visibility IN ('organization','restricted')")
    op.add_column("key_results", sa.Column("evidence_source", sa.Unicode(255), server_default=sa.text("N'人工更新'"), nullable=False))


def downgrade():
    raise RuntimeError("Removing visibility would expose restricted objectives; downgrade is disabled")
