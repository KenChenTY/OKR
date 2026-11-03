import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.config import Settings
from app.db import Base
from app.evidence import validate_content
from app.main import app
from app.models import Objective
from app.security import can_read, require_owner
from app.services import check_version, etag
from app.worker import csv_safe


def test_production_forbids_dev_auth():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, env="production", auth_mode="development", enable_dev_login=True)


def test_sqlite_is_not_a_fallback():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite://")


def test_live_probe_without_database():
    result = TestClient(app).get("/health/live")
    assert result.status_code == 200
    assert result.json()["status"] == "alive"
    assert result.headers["x-request-id"]


def test_openapi_documents_main_workflows():
    paths = app.openapi()["paths"]
    assert "/api/v1/objectives/{objective_id}/submit" in paths
    assert "/api/v1/key-results/{kr_id}/check-ins" in paths
    assert "/api/v1/evidence/versions/{evidence_id}/download" in paths


def test_schema_compiles_for_sql_server():
    dialect = mssql.dialect()
    statements = [str(CreateTable(table).compile(dialect=dialect)) for table in Base.metadata.sorted_tables]
    assert any("ROWVERSION" in sql for sql in statements)
    assert any("NVARCHAR(max)" in sql for sql in statements)
    indexes = [str(CreateIndex(i).compile(dialect=dialect)) for t in Base.metadata.tables.values() for i in t.indexes]
    assert any("WHERE status = 'Pending'" in sql for sql in indexes)


def test_employee_cannot_read_another_owner():
    from types import SimpleNamespace

    employee = SimpleNamespace(id=1, role="Employee")
    assert not can_read(None, employee, SimpleNamespace(owner_id=2))
    assert can_read(None, employee, SimpleNamespace(owner_id=1))
    with pytest.raises(Exception) as exc:
        require_owner(employee, SimpleNamespace(owner_id=2))
    assert exc.value.status_code == 403


def test_admin_has_no_implicit_business_access():
    from types import SimpleNamespace

    assert not can_read(None, SimpleNamespace(role="System Admin"), SimpleNamespace(owner_id=1))


def test_restricted_objective_is_not_exposed_by_manager_role():
    from types import SimpleNamespace
    from unittest.mock import Mock

    db = Mock()
    db.get.return_value = None
    manager = SimpleNamespace(id=1, role="Manager", org_id=10)
    target = SimpleNamespace(id=2, owner_id=3, org_id=10, visibility="restricted")
    assert not can_read(db, manager, target)
    db.get.return_value = object()
    assert can_read(db, manager, target)


def test_production_rejects_unencrypted_database_configuration():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            env="production",
            public_url="https://okr.example.com",
            tenant_id="tenant",
            client_id="client",
            client_secret="not-a-real-secret",
            database_url="mssql+pyodbc://server/OKR?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=no&TrustServerCertificate=yes",
        )


def test_etag_is_quoted_binary_version():
    obj = Objective(row_version=b"\x00\x00\x00\x01")
    assert etag(obj) == '"AAAAAQ=="'


def test_concurrent_update_requires_fresh_etag():
    from types import SimpleNamespace

    obj = Objective(row_version=b"\x00\x00\x00\x02")
    with pytest.raises(Exception) as missing:
        check_version(obj, SimpleNamespace(headers={}))
    assert missing.value.status_code == 428
    with pytest.raises(Exception) as stale:
        check_version(obj, SimpleNamespace(headers={"if-match": '"AAAAAQ=="'}))
    assert stale.value.status_code == 412
    check_version(obj, SimpleNamespace(headers={"if-match": etag(obj)}))


def test_business_routes_require_session_without_opening_database():
    client = TestClient(app)
    for path in ("/api/v1/objectives", "/api/v1/benefits", "/api/v1/admin/jobs", "/api/v1/exports"):
        assert client.get(path).status_code == 401


def test_evidence_rejects_disguised_files(tmp_path: Path):
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"not a pdf")
    assert not validate_content(path, ".pdf")
    assert not validate_content(path, ".xlsx")
    path.write_bytes(b"%PDF-1.7\n")
    assert validate_content(path, ".pdf")


def test_office_macro_and_zip_validation(tmp_path: Path):
    path = tmp_path / "file.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "xml")
        archive.writestr("xl/workbook.xml", "xml")
    assert validate_content(path, ".xlsx")
    assert not validate_content(path, ".pptx")
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("xl/vbaProject.bin", "macro")
    assert not validate_content(path, ".xlsx")


@pytest.mark.parametrize("value", ["=SUM(A1:A2)", "+cmd", "-2+3", "@SUM(A1)", "  =1", "\t=1"])
def test_csv_formula_injection(value):
    assert csv_safe(value).startswith("'")


def test_csv_plain_text():
    assert csv_safe("运营效率") == "运营效率"
    assert csv_safe(None) == ""
