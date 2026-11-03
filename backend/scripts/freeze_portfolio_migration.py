"""Freeze portfolio schema as an independent upgrade."""

from pathlib import Path

from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateIndex, CreateTable

from app import models  # noqa: F401
from app.db import Base

target = Path("migrations/versions/0003_portfolio.py")
if target.exists():
    raise SystemExit("Revision already exists; refusing to rewrite history")
names = {"initiatives", "external_project_links", "benefits", "benefit_allocations", "benefit_claims", "benefit_verifications"}
ddl = []
for table in Base.metadata.sorted_tables:
    if table.name in names:
        ddl.append(str(CreateTable(table).compile(dialect=mssql.dialect())).strip())
        ddl.extend(str(CreateIndex(i).compile(dialect=mssql.dialect())) for i in sorted(table.indexes, key=lambda i: i.name))
target.write_text(
    '''"""Add initiatives, project links, benefits and independent verification."""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
'''
    + "\n".join("    op.execute(" + repr(s) + ")" for s in ddl)
    + """


def downgrade():
    raise RuntimeError("Benefit evidence and verification history must not be discarded")
""",
    encoding="utf-8",
)
print("Frozen portfolio migration")
