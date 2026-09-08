"""Pydantic configuration models for Artifact Hub.

The shape intentionally follows DataMind's ``config_objects`` module. A
``HubConfig`` document provides the top-level ``config`` object, while
repository adapters only need the nested storage configuration.
"""

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


StorageModeType = Literal["sqlite", "mysql", "server"]


class SqliteStorageConfig(BaseModel):
    """Local SQLite persistence settings."""

    model_config = ConfigDict(extra="forbid")

    path: Path = Field(
        Path("data/hub.sqlite3"),
        description="SQLite database file path",
    )


class ServerStorageConfig(BaseModel):
    """Server-side MySQL-compatible database settings.

    ``server`` is the DataMind-compatible configuration name. Hub accepts
    both ``storage.mode='mysql'`` and ``storage.mode='server'``; the latter
    is an alias kept for configuration compatibility with DataMind.
    """

    model_config = ConfigDict(extra="forbid")

    url: Optional[str] = Field(
        None,
        description="Optional SQLAlchemy URL; takes precedence over host fields",
    )
    host: str = Field("127.0.0.1", description="Database host")
    port: int = Field(3306, description="Database port")
    user: str = Field("dsh_artifact_hub", description="Database username")
    password: str = Field("", description="Database password")
    db: str = Field("dsh_artifact_hub", description="Database name")
    charset: str = Field("utf8mb4", description="Connection charset")
    pool_size: int = Field(5, description="SQLAlchemy connection pool size")
    max_overflow: int = Field(10, description="SQLAlchemy max overflow connections")


class StorageConfig(BaseModel):
    """Database selection and adapter-specific configuration."""

    model_config = ConfigDict(extra="forbid")

    mode: StorageModeType = Field(
        "sqlite",
        description="Storage mode: 'sqlite', 'mysql', or DataMind-compatible 'server'",
    )
    sqlite: SqliteStorageConfig = Field(default_factory=SqliteStorageConfig)
    server: Optional[ServerStorageConfig] = Field(
        default_factory=ServerStorageConfig,
        description="MySQL-compatible server configuration",
    )

    @property
    def uses_server(self) -> bool:
        """Whether the configured repository should use the server adapter."""

        return self.mode in {"mysql", "server"}


class HubSettings(BaseModel):
    """Runtime settings nested under the top-level ``config`` object."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field("127.0.0.1", description="HTTP bind host")
    port: int = Field(8000, description="HTTP bind port")
    base_url: Optional[str] = Field(
        None,
        description="Public URL used when constructing share links",
    )
    artifact_root: Path = Field(
        Path("data/artifacts"),
        description="Immutable Artifact storage root",
    )
    storage: StorageConfig = Field(default_factory=StorageConfig)

    def model_post_init(self, _context) -> None:
        if self.base_url is None:
            object.__setattr__(self, "base_url", f"http://{self.host}:{self.port}")


class HubConfig(BaseModel):
    """Top-level Artifact Hub configuration document."""

    model_config = ConfigDict(extra="forbid")

    config: HubSettings = Field(default_factory=HubSettings)


# Compatibility name for callers that imported the first MVP MySQL settings.
MysqlSettings = ServerStorageConfig
