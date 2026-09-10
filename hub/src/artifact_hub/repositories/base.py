"""Database-independent repository interface for Artifact Hub metadata."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping, Optional


Record = Dict[str, Any]
Values = Mapping[str, object]


class ArtifactRepository(ABC):
    """Persistence interface shared by SQLite and MySQL adapters."""

    @abstractmethod
    def close(self) -> None:
        """Release database resources owned by this repository."""

    @abstractmethod
    def create_artifact(self, values: Values) -> None:
        """Persist a logical Artifact."""

    @abstractmethod
    def get_artifact(self, artifact_id: str) -> Optional[Record]:
        """Return an Artifact record or None."""

    @abstractmethod
    def get_artifact_by_source(
        self, source_session_id: str, source_path: str, created_by_id: str
    ) -> Optional[Record]:
        """Return the stable Artifact identity for one creator's Session File."""

    @abstractmethod
    def next_version(self, artifact_id: str) -> int:
        """Return the next version number, including reserved NAS uploads."""

    @abstractmethod
    def create_version(self, values: Values) -> None:
        """Persist an immutable Artifact Version."""

    @abstractmethod
    def get_latest_version(self, artifact_id: str) -> Optional[Record]:
        """Return the newest committed Artifact Version or None."""

    @abstractmethod
    def upsert_share(self, values: Values) -> None:
        """Create or overwrite the single Share for an Artifact Version."""

    @abstractmethod
    def create_upload(self, values: Values) -> None:
        """Persist a prepared NAS upload."""

    @abstractmethod
    def get_upload(self, upload_id: str) -> Optional[Record]:
        """Return a NAS upload reservation or None."""

    @abstractmethod
    def mark_upload_committed(self, upload_id: str) -> bool:
        """Atomically transition a prepared upload to committed."""

    @abstractmethod
    def get_share_by_token_hash(self, token_hash: str) -> Optional[Record]:
        """Return the joined Share view for a hashed token or None."""

    @abstractmethod
    def get_share_by_id(self, share_id: str) -> Optional[Record]:
        """Return the joined Share view for a business Share ID or None."""

    @abstractmethod
    def get_share_by_version_id(self, artifact_version_id: str) -> Optional[Record]:
        """Return the joined Share view for an Artifact Version or None."""

    @abstractmethod
    def list_shares_by_creator(self, created_by_id: str) -> List[Record]:
        """List shares created by one trusted caller identity."""

    @abstractmethod
    def revoke_share(self, share_id: str, revoked_at: str) -> bool:
        """Revoke an active Share and report whether it changed."""
