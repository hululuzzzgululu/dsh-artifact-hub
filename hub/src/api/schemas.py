"""Pydantic request and response models for the Artifact Hub API."""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class LocalShareRequest(BaseModel):
    session_id: str = Field(min_length=1)
    workspace_root: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    created_by_id: str = Field(min_length=1, max_length=128)
    created_by_name: Optional[str] = Field(default=None, max_length=128)
    dsh_workspace_id: Optional[str] = Field(default=None, max_length=128)
    dsh_workspace_path: Optional[str] = Field(default=None, max_length=512)
    dsh_workspace_title: Optional[str] = Field(default=None, max_length=255)
    artifact_id: Optional[str] = None
    name: Optional[str] = None
    artifact_type: Optional[str] = None
    visibility: Literal["LINK"] = "LINK"
    permission: Literal["VIEW_DOWNLOAD"] = "VIEW_DOWNLOAD"
    expires_at: Optional[str] = None


class NasPrepareRequest(BaseModel):
    session_id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    created_by_id: str = Field(min_length=1, max_length=128)
    created_by_name: Optional[str] = Field(default=None, max_length=128)
    dsh_workspace_id: Optional[str] = Field(default=None, max_length=128)
    dsh_workspace_path: Optional[str] = Field(default=None, max_length=512)
    dsh_workspace_title: Optional[str] = Field(default=None, max_length=255)
    artifact_id: Optional[str] = None
    name: Optional[str] = None
    artifact_type: Optional[str] = None


class NasCommitRequest(BaseModel):
    upload_id: str = Field(min_length=1)
    created_by_id: str = Field(min_length=1, max_length=128)
    created_by_name: Optional[str] = Field(default=None, max_length=128)
    visibility: Literal["LINK"] = "LINK"
    permission: Literal["VIEW_DOWNLOAD"] = "VIEW_DOWNLOAD"
    expires_at: Optional[str] = None
    checksum: Optional[str] = None


class RevokeShareRequest(BaseModel):
    token: str = Field(min_length=1)
    revoked_by_id: str = Field(min_length=1, max_length=128)


class ShareResponse(BaseModel):
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
    token: Optional[str] = None


class PublicShareResponse(BaseModel):
    """Minimum metadata needed to render the public share page."""

    version: int
    name: str
    mime_type: str
    size: int
    visibility: Literal["LINK"]
    permission: Literal["VIEW_DOWNLOAD"]
    created_by_id: str
    created_by_name: str
    expires_at: Optional[str]
    created_at: str


class PreparedUploadResponse(BaseModel):
    upload_id: str
    artifact_id: str
    version: int
    storage_mode: str
    storage_key: str
    target_path: str
    name: str


ShareList = Dict[str, List[ShareResponse]]
