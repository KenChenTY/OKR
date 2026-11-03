"""Explicit database creation, Alembic upgrade, and runtime role provisioning."""

import os
from pathlib import Path
import re
import subprocess
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    # This helper is scoped to the bundled private trial deployment.
    url = make_url(os.environ["OKR_DATABASE_URL"])
    if url.username != "sa" or url.database != "OKR" or os.environ.get("OKR_ENV") != "development":
        raise SystemExit("Use the Compose admin service with its trial configuration")
    password = os.environ["OKR_APP_PASSWORD"]
    if not re.fullmatch(r"[A-Za-z0-9]{20,128}", password):
        raise SystemExit("Generate a 20–128 character ASCII alphanumeric application password using the guide")

    master = create_engine(url.set(database="master"), isolation_level="AUTOCOMMIT", hide_parameters=True)
    with master.connect() as db:
        db.exec_driver_sql("IF DB_ID(N'OKR') IS NULL CREATE DATABASE [OKR]")
    master.dispose()

    # The API and Worker deliberately never run migrations on startup.
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

    master = create_engine(url.set(database="master"), hide_parameters=True)
    with master.begin() as db:
        # The password is validated as alphanumeric above; never log the DDL.
        db.exec_driver_sql(
            "IF SUSER_ID(N'okr_app') IS NULL "
            f"CREATE LOGIN [okr_app] WITH PASSWORD = '{password}', CHECK_POLICY = ON"
        )
    master.dispose()

    owner = create_engine(url, hide_parameters=True)
    with owner.begin() as db:
        script = Path("runtime-role.sql").read_text(encoding="utf-8")
        for batch in re.split(r"(?im)^GO\s*$", script):
            if batch.strip():
                db.exec_driver_sql(batch)
        db.exec_driver_sql("IF USER_ID(N'okr_app') IS NULL CREATE USER [okr_app] FOR LOGIN [okr_app]")
        db.exec_driver_sql(
            "IF IS_ROLEMEMBER(N'okr_runtime', N'okr_app') <> 1 "
            "ALTER ROLE [okr_runtime] ADD MEMBER [okr_app]"
        )
    owner.dispose()

    runtime = create_engine(url.set(username="okr_app", password=password), hide_parameters=True)
    with runtime.connect() as db:
        version = db.execute(text("SELECT TOP 1 version_num FROM alembic_version")).scalar_one()
    runtime.dispose()
    print(f"OKR database ready at migration {version}; runtime login okr_app verified.")
    print("Existing login passwords are not changed. Initialize the first administrator using the guide.")


if __name__ == "__main__":
    main()
