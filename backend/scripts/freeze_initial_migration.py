"""One-time bootstrap generator. Never regenerate an already deployed revision."""

from pathlib import Path

from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateIndex, CreateTable

from app import models  # noqa: F401
from app.db import Base

target = Path("migrations/versions/0001_initial.py")
if target.exists():
    raise SystemExit("Initial migration already exists; refusing to rewrite history")
target.parent.mkdir(parents=True, exist_ok=True)
dialect = mssql.dialect()
ddl = []
for table in Base.metadata.sorted_tables:
    ddl.append(str(CreateTable(table).compile(dialect=dialect)).strip())
    ddl.extend(str(CreateIndex(index).compile(dialect=dialect)) for index in sorted(table.indexes, key=lambda i: i.name))
header = '''"""Initial SQL Server schema, frozen at implementation time."""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
'''
body = "\n".join("    op.execute(" + repr(statement) + ")" for statement in ddl)
footer = """


def downgrade():
    raise RuntimeError("Initial schema rollback is destructive; restore a verified backup instead")
"""
target.write_text(header + body + footer, encoding="utf-8")
Path("../deploy/sql/001-initial-schema.sql").write_text(
    "-- Review-only SQL Server schema. Deploy with Alembic to retain version tracking.\n\n" + "\nGO\n\n".join(ddl) + "\nGO\n", encoding="utf-8"
)
print(f"Frozen {len(Base.metadata.tables)} tables and indexes")
