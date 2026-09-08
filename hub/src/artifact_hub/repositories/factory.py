"""Create the configured Artifact Hub repository adapter."""

from config.config_objects import HubSettings

from .base import ArtifactRepository
from .mysql import MysqlArtifactRepository
from .sqlite import SqliteArtifactRepository


def create_artifact_repository(settings: HubSettings) -> ArtifactRepository:
    """Build one repository adapter from runtime storage configuration."""

    if settings.storage.uses_server:
        if settings.storage.server is None:
            raise ValueError("server storage configuration is required")
        return MysqlArtifactRepository.from_config(settings.storage.server)
    return SqliteArtifactRepository(settings.storage.sqlite.path)
