"""Runtime configuration loading for Artifact Hub."""

import os
from collections.abc import Mapping
from typing import Optional

from .config_objects import HubConfig, HubSettings, ServerStorageConfig, StorageConfig


class ConfigManager:
    """Build a validated ``HubConfig`` from environment variables.

    The configuration object is the public seam. Environment parsing stays
    here so API startup and tests do not need to know variable names.
    """

    def __init__(self, environ: Optional[Mapping[str, str]] = None):
        self._environ = os.environ if environ is None else environ

    def load(self) -> HubConfig:
        env = self._environ
        host = env.get("HUB_HOST", "127.0.0.1")
        port = int(env.get("HUB_PORT", "8000"))
        return HubConfig(
            config=HubSettings(
                host=host,
                port=port,
                base_url=env.get("HUB_BASE_URL"),
                artifact_root=env.get("HUB_ARTIFACT_ROOT", "data/artifacts"),
                storage=StorageConfig(
                    mode=env.get("HUB_STORAGE_MODE", "sqlite").lower(),
                    sqlite={
                        "path": env.get("HUB_DATABASE_PATH", "data/hub.sqlite3"),
                    },
                    server=ServerStorageConfig(
                        url=env.get("HUB_MYSQL_URL"),
                        host=env.get("HUB_MYSQL_HOST", "127.0.0.1"),
                        port=int(env.get("HUB_MYSQL_PORT", "3306")),
                        user=env.get("HUB_MYSQL_USER", "dsh_artifact_hub"),
                        password=env.get("HUB_MYSQL_PASSWORD", ""),
                        db=env.get("HUB_MYSQL_DATABASE", "dsh_artifact_hub"),
                        charset=env.get("HUB_MYSQL_CHARSET", "utf8mb4"),
                        pool_size=int(env.get("HUB_MYSQL_POOL_SIZE", "5")),
                        max_overflow=int(env.get("HUB_MYSQL_MAX_OVERFLOW", "10")),
                    ),
                ),
            ),
        )

    @classmethod
    def from_env(cls) -> HubConfig:
        """Load the process environment using the default manager."""

        return cls().load()


config_manager = ConfigManager()


def get_config() -> HubConfig:
    """Return the current process configuration."""

    return config_manager.load()
