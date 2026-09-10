"""Pydantic domain models returned by the Artifact Hub service."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Immutable domain result model with strict fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ShareInfo(DomainModel):
    share_id: str
    artifact_id: str
    artifact_version_id: str
    version: int
    name: str
    source_session_id: str
    source_path: str
    mime_type: str
    storage_mode: str
    storage_key: str
    size: int
    checksum: str
    visibility: Literal["LINK"]
    permission: Literal["VIEW_DOWNLOAD"]
    created_by_id: str
    created_by_name: str
    expires_at: Optional[str]
    revoked_at: Optional[str]
    created_at: str
    url: Optional[str]
    share_url: Optional[str]

    def to_dict(self):
        return self.model_dump()


class ShareResult(ShareInfo):
    token: str = ""

    def to_dict(self):
        return self.model_dump()


class PreparedUpload(DomainModel):
    upload_id: str
    artifact_id: str
    version: int
    storage_mode: str
    storage_key: str
    target_path: str
    name: str

    def to_dict(self):
        return self.model_dump()


class ContentResult(DomainModel):
    body: bytes
    name: str
    mime_type: str
    permission: Literal["VIEW_DOWNLOAD"]
