"""Local account credentials and shared login throttling."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import DATETIME2

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "local_credentials",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("username", sa.Unicode(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.Unicode(255), nullable=False),
    )
    op.create_table(
        "login_attempts",
        sa.Column("key", sa.Unicode(64), primary_key=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("window_start", DATETIME2(3), nullable=False),
    )


def downgrade():
    raise RuntimeError("Credential deletion requires a separate reviewed migration")
