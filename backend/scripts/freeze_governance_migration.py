"""Freeze the incremental governance tables; never rewrite an existing revision."""

from pathlib import Path

from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateIndex, CreateTable

from app import models  # noqa: F401
from app.db import Base

target = Path("migrations/versions/0002_governance.py")
if target.exists():
    raise SystemExit("Revision already exists; refusing to rewrite history")
names = {"objective_grants", "change_requests", "exports", "score_snapshots"}
ddl = []
for table in Base.metadata.sorted_tables:
    if table.name in names:
        ddl.append(str(CreateTable(table).compile(dialect=mssql.dialect())).strip())
        ddl.extend(str(CreateIndex(i).compile(dialect=mssql.dialect())) for i in sorted(table.indexes, key=lambda i: i.name))
target.write_text(
    '''"""Add approved changes, object readers, exports and score history."""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
'''
    + "\n".join("    op.execute(" + repr(s) + ")" for s in ddl)
    + """


def downgrade():
    raise RuntimeError("Governance history must not be discarded; restore a verified backup")
""",
    encoding="utf-8",
)
print("Frozen governance migration")
