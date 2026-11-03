from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OKR_", env_file=".env", extra="ignore", hide_input_in_errors=True)
    env: Literal["development", "test", "production"] = "development"
    database_url: str = "mssql+pyodbc://localhost/OKR?driver=ODBC+Driver+18+for+SQL+Server&Trusted_Connection=yes&Encrypt=yes&TrustServerCertificate=no"
    auth_mode: Literal["entra", "development", "password"] = "password"
    enable_dev_login: bool = False
    public_url: str = "http://localhost:5173"
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    storage_root: Path = Path("../var")
    link_hosts: str = "app.powerbi.com"
    project_link_hosts: str = "dev.azure.com,tasks.office.com,planner.cloud.microsoft"
    scanner_executable: str = ""
    business_timezone: str = "Asia/Shanghai"
    health_grace_days: int = Field(default=3, ge=0, le=30)
    health_red_confidence: int = Field(default=40, ge=0, le=100)
    health_amber_confidence: int = Field(default=70, ge=0, le=100)
    health_red_lag: int = Field(default=20, ge=0, le=100)
    health_amber_lag: int = Field(default=10, ge=0, le=100)

    @model_validator(mode="after")
    def secure_configuration(self):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(self.business_timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("Invalid business timezone") from None
        if self.health_red_confidence >= self.health_amber_confidence or self.health_red_lag <= self.health_amber_lag:
            raise ValueError("Health thresholds must be ordered")
        if not self.database_url.startswith("mssql+pyodbc://"):
            raise ValueError("Only SQL Server via pyodbc is supported")
        if self.env == "production":
            from sqlalchemy.engine import make_url

            query = {k.lower(): str(v).lower() for k, v in make_url(self.database_url).query.items()}
            if "odbc_connect" in query:
                query = {p.split("=", 1)[0].strip().lower(): p.split("=", 1)[1].strip().lower() for p in query["odbc_connect"].split(";") if "=" in p}
            if query.get("encrypt") not in ("yes", "true", "mandatory", "strict") or query.get("trustservercertificate") not in ("no", "false"):
                raise ValueError("Production SQL requires explicit encryption and certificate verification")
            if self.auth_mode == "development" or self.enable_dev_login:
                raise ValueError("Development authentication is forbidden in production")
            if not self.public_url.startswith("https://"):
                raise ValueError("Production requires HTTPS")
            if self.auth_mode == "entra" and not all((self.tenant_id, self.client_id, self.client_secret)):
                raise ValueError("Production requires Entra configuration")
        return self


@lru_cache
def settings():
    return Settings()
