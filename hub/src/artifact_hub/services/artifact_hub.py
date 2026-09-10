import base64
import hashlib
import hmac
import mimetypes
import secrets
import threading
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from ..common.identifiers import hash_token, new_id
from ..common.time import now_iso, parse_iso
from ..domain.errors import (
    AccessRestrictedError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ShareExpiredError,
    ShareRevokedError,
    ValidationError,
)
from ..domain.models import ContentResult, PreparedUpload, ShareInfo, ShareResult
from ..repositories.base import ArtifactRepository
from ..storage.filesystem import FilesystemStorage


def _serialized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._operation_lock:
            return method(self, *args, **kwargs)

    return wrapper


class ArtifactHub:
    """Application service for immutable artifacts and access Shares."""

    _PREVIEW_TTL_SECONDS = 10 * 60

    def __init__(
        self,
        repository: ArtifactRepository,
        artifact_root,
        base_url="http://localhost:8000",
        preview_secret=None,
    ):
        self.repository = repository
        self.storage = FilesystemStorage(artifact_root)
        self.base_url = base_url.rstrip("/")
        self._preview_secret = preview_secret or secrets.token_bytes(32)
        self._operation_lock = threading.RLock()

    def close(self):
        self.repository.close()

    @_serialized
    def create_local_share(
        self,
        session_id,
        workspace_root,
        source_path,
        created_by_id,
        created_by_name=None,
        dsh_workspace_id=None,
        dsh_workspace_path=None,
        dsh_workspace_title=None,
        artifact_id=None,
        name=None,
        artifact_type=None,
        visibility="LINK",
        permission="VIEW_DOWNLOAD",
        expires_at=None,
    ):
        self._validate_share_options(visibility, permission)
        self._validate_expiry(expires_at)
        created_by_id, created_by_name = self._creator(
            created_by_id, created_by_name
        )
        dsh_workspace_path = dsh_workspace_path or str(
            Path(workspace_root).expanduser().resolve()
        )
        self._validate_workspace_metadata(
            dsh_workspace_id, dsh_workspace_path, dsh_workspace_title
        )
        source = self.storage.source_path(workspace_root, source_path)
        if not source.is_file():
            raise NotFoundError("source Session File does not exist")

        artifact, version, artifact_is_new = self._artifact_for_snapshot(
            artifact_id=artifact_id,
            session_id=session_id,
            source_path=source_path,
            created_by_id=created_by_id,
            created_by_name=created_by_name,
            dsh_workspace_id=dsh_workspace_id,
            dsh_workspace_path=dsh_workspace_path,
            dsh_workspace_title=dsh_workspace_title,
            name=name or Path(source_path).name,
            artifact_type=artifact_type,
        )
        final_name = artifact["name"]
        storage_key = self.storage.storage_key(
            created_by_id, artifact["artifact_id"], version, final_name
        )
        self.storage.copy_snapshot(source, storage_key)
        try:
            size, checksum = self.storage.inspect(storage_key)
            latest = (
                None
                if artifact_is_new
                else self.repository.get_latest_version(artifact["artifact_id"])
            )
            if latest is not None and latest["checksum"] == checksum:
                self.storage.discard(storage_key)
                return self._share_existing_version(
                    artifact=artifact,
                    version=latest,
                    visibility=visibility,
                    permission=permission,
                    expires_at=expires_at,
                    created_by_id=created_by_id,
                    created_by_name=created_by_name,
                )
            return self._publish_snapshot(
                artifact=artifact,
                version=version,
                storage_mode="LOCAL",
                storage_key=storage_key,
                size=size,
                checksum=checksum,
                visibility=visibility,
                permission=permission,
                expires_at=expires_at,
                created_by_id=created_by_id,
                created_by_name=created_by_name,
                artifact_is_new=artifact_is_new,
            )
        except Exception:
            self.storage.discard(storage_key)
            raise

    @_serialized
    def prepare_nas_share(
        self,
        session_id,
        source_path,
        created_by_id,
        created_by_name=None,
        dsh_workspace_id=None,
        dsh_workspace_path=None,
        dsh_workspace_title=None,
        artifact_id=None,
        name=None,
        artifact_type=None,
    ):
        created_by_id, created_by_name = self._creator(
            created_by_id, created_by_name
        )
        self._validate_workspace_metadata(
            dsh_workspace_id, dsh_workspace_path, dsh_workspace_title
        )
        self.storage.validate_source_path(source_path)
        artifact, version, artifact_is_new = self._artifact_for_snapshot(
            artifact_id=artifact_id,
            session_id=session_id,
            source_path=source_path,
            created_by_id=created_by_id,
            created_by_name=created_by_name,
            dsh_workspace_id=dsh_workspace_id,
            dsh_workspace_path=dsh_workspace_path,
            dsh_workspace_title=dsh_workspace_title,
            name=name or Path(source_path).name,
            artifact_type=artifact_type,
        )
        if artifact_is_new:
            self.repository.create_artifact(self._artifact_values(artifact))
        storage_key = self.storage.storage_key(
            created_by_id, artifact["artifact_id"], version, artifact["name"]
        )
        upload_id = self._id("upl")
        self.repository.create_upload(
            {
                "upload_id": upload_id,
                "artifact_id": artifact["artifact_id"],
                "version": version,
                "storage_mode": "NAS",
                "storage_key": storage_key,
                "source_session_id": session_id,
                "source_path": str(Path(source_path)),
                "name": artifact["name"],
                "artifact_type": artifact["artifact_type"],
                "created_by_id": created_by_id,
                "created_by_name": created_by_name,
                "created_at": self._now(),
                "state": "PREPARED",
            }
        )
        return PreparedUpload(
            upload_id=upload_id,
            artifact_id=artifact["artifact_id"],
            version=version,
            storage_mode="NAS",
            storage_key=storage_key,
            target_path=str(self.storage.target_path(storage_key)),
            name=artifact["name"],
        )

    @_serialized
    def commit_nas_share(
        self,
        upload_id,
        created_by_id,
        created_by_name=None,
        visibility="LINK",
        permission="VIEW_DOWNLOAD",
        expires_at=None,
        checksum=None,
    ):
        created_by_id, created_by_name = self._creator(
            created_by_id, created_by_name
        )
        upload = self.repository.get_upload(upload_id)
        if upload is None:
            raise NotFoundError("NAS upload does not exist")
        if upload["created_by_id"] != created_by_id:
            raise ForbiddenError("only the upload creator can commit it")
        if upload["state"] != "PREPARED":
            raise ConflictError("NAS upload has already been committed")
        self._validate_share_options(visibility, permission)
        self._validate_expiry(expires_at)
        size, actual_checksum = self.storage.inspect(upload["storage_key"])
        if checksum is not None and checksum != actual_checksum:
            raise ValidationError("checksum does not match the NAS file")

        artifact = self.repository.get_artifact(upload["artifact_id"])
        if artifact is None:
            raise NotFoundError("Artifact does not exist")
        version_id = self._id("av")
        now = self._now()
        self.repository.create_version(
            {
                "artifact_version_id": version_id,
                "artifact_id": upload["artifact_id"],
                "version": upload["version"],
                "mime_type": self._mime_type(upload["name"]),
                "storage_mode": "NAS",
                "storage_key": upload["storage_key"],
                "entrypoint": upload["name"],
                "size_bytes": size,
                "checksum": actual_checksum,
                "created_by_id": created_by_id,
                "created_by_name": created_by_name,
                "created_at": now,
            }
        )
        result = self._upsert_share(
            artifact=artifact,
            version_id=version_id,
            version=upload["version"],
            name=upload["name"],
            mime_type=self._mime_type(upload["name"]),
            storage_mode="NAS",
            storage_key=upload["storage_key"],
            size=size,
            checksum=actual_checksum,
            visibility=visibility,
            permission=permission,
            expires_at=expires_at,
            created_by_id=created_by_id,
            created_by_name=created_by_name,
            created_at=now,
        )
        if not self.repository.mark_upload_committed(upload_id):
            raise ConflictError("NAS upload has already been committed")
        return result

    def resolve_share(self, token):
        row = self._share_row(token)
        if row["revoked_at"] is not None:
            raise ShareRevokedError("share has been revoked")
        if self._is_expired(row["expires_at"]):
            raise ShareExpiredError("share has expired")
        if row["visibility"] != "LINK" or row["permission"] != "VIEW_DOWNLOAD":
            raise AccessRestrictedError("share access mode is no longer supported")
        return self._share_info(row, token=token)

    def read_share_content(self, token):
        info = self.resolve_share(token)
        with self.storage.open(info.storage_key) as stream:
            return ContentResult(
                body=stream.read(),
                name=info.name,
                mime_type=info.mime_type,
                permission=info.permission,
            )

    def list_created_shares(self, created_by_id):
        created_by_id, _created_by_name = self._creator(created_by_id)
        return [
            self._share_info(
                row,
                token=(
                    self._preview_token(row["share_id"])
                    if row["revoked_at"] is None
                    and not self._is_expired(row["expires_at"])
                    else None
                ),
            )
            for row in self.repository.list_shares_by_creator(created_by_id)
            if row["visibility"] == "LINK" and row["permission"] == "VIEW_DOWNLOAD"
        ]

    @_serialized
    def revoke_share(self, token, revoked_by_id):
        revoked_by_id, _revoked_by_name = self._creator(revoked_by_id)
        row = self._share_row(token, allow_preview=False)
        if row["share_created_by_id"] != revoked_by_id:
            raise ForbiddenError("only the share creator can revoke it")
        if not self.repository.revoke_share(row["share_id"], self._now()):
            raise ConflictError("share has already been revoked")

    def _artifact_for_snapshot(
        self,
        artifact_id,
        session_id,
        source_path,
        created_by_id,
        created_by_name,
        dsh_workspace_id,
        dsh_workspace_path,
        dsh_workspace_title,
        name,
        artifact_type,
    ):
        if artifact_id is not None:
            artifact = self.repository.get_artifact(artifact_id)
            if artifact is None:
                raise NotFoundError("Artifact does not exist")
            if artifact["created_by_id"] != created_by_id:
                raise ForbiddenError("only the artifact creator can create another version")
            if artifact["source_session_id"] != session_id or artifact["source_path"] != str(Path(source_path)):
                raise ValidationError("a new version must use the Artifact's source Session File")
            return artifact, self.repository.next_version(artifact_id), False

        source_path = str(Path(source_path))
        artifact = self.repository.get_artifact_by_source(
            session_id, source_path, created_by_id
        )
        if artifact is not None:
            return artifact, self.repository.next_version(artifact["artifact_id"]), False

        self._validate_name(name)
        return (
            {
                "artifact_id": self._id("art"),
                "source_session_id": session_id,
                "source_path": source_path,
                "name": name,
                "artifact_type": artifact_type,
                "dsh_workspace_id": dsh_workspace_id,
                "dsh_workspace_path": dsh_workspace_path,
                "dsh_workspace_title": dsh_workspace_title,
                "created_by_id": created_by_id,
                "created_by_name": created_by_name,
                "created_at": self._now(),
                "status": "ACTIVE",
            },
            1,
            True,
        )

    def _share_existing_version(
        self,
        artifact,
        version,
        visibility,
        permission,
        expires_at,
        created_by_id,
        created_by_name,
    ):
        return self._upsert_share(
            artifact=artifact,
            version_id=version["artifact_version_id"],
            version=version["version"],
            name=artifact["name"],
            mime_type=version["mime_type"],
            storage_mode=version["storage_mode"],
            storage_key=version["storage_key"],
            size=version["size_bytes"],
            checksum=version["checksum"],
            visibility=visibility,
            permission=permission,
            expires_at=expires_at,
            created_by_id=created_by_id,
            created_by_name=created_by_name,
            created_at=self._now(),
        )

    def _publish_snapshot(
        self,
        artifact,
        version,
        storage_mode,
        storage_key,
        size,
        checksum,
        visibility,
        permission,
        expires_at,
        created_by_id,
        created_by_name,
        artifact_is_new,
    ):
        if artifact_is_new:
            self.repository.create_artifact(self._artifact_values(artifact))
        version_id = self._id("av")
        now = self._now()
        mime_type = self._mime_type(artifact["name"])
        self.repository.create_version(
            {
                "artifact_version_id": version_id,
                "artifact_id": artifact["artifact_id"],
                "version": version,
                "mime_type": mime_type,
                "storage_mode": storage_mode,
                "storage_key": storage_key,
                "entrypoint": artifact["name"],
                "size_bytes": size,
                "checksum": checksum,
                "created_by_id": created_by_id,
                "created_by_name": created_by_name,
                "created_at": now,
            }
        )
        return self._upsert_share(
            artifact=artifact,
            version_id=version_id,
            version=version,
            name=artifact["name"],
            mime_type=mime_type,
            storage_mode=storage_mode,
            storage_key=storage_key,
            size=size,
            checksum=checksum,
            visibility=visibility,
            permission=permission,
            expires_at=expires_at,
            created_by_id=created_by_id,
            created_by_name=created_by_name,
            created_at=now,
        )

    def _upsert_share(
        self,
        artifact,
        version_id,
        version,
        name,
        mime_type,
        storage_mode,
        storage_key,
        size,
        checksum,
        visibility,
        permission,
        expires_at,
        created_by_id,
        created_by_name,
        created_at,
    ):
        self._validate_expiry(expires_at)
        existing = self.repository.get_share_by_version_id(version_id)
        if existing is not None and existing["revoked_at"] is None and existing["token"]:
            # Idempotent re-share of one version: keep the link alive.
            token = existing["token"]
        else:
            # New version, revoked share, or pre-token legacy row: fresh link.
            token = secrets.token_urlsafe(32)
        self.repository.upsert_share(
            {
                "share_id": existing["share_id"] if existing is not None else self._id("shr"),
                "artifact_version_id": version_id,
                "token_hash": self._token_hash(token),
                "token": token,
                "visibility": visibility,
                "permission": permission,
                "expires_at": expires_at,
                "revoked_at": None,
                "created_by_id": created_by_id,
                "created_by_name": created_by_name,
                "created_at": existing["share_created_at"] if existing is not None else created_at,
                "updated_at": created_at,
            }
        )
        row = self.repository.get_share_by_token_hash(self._token_hash(token))
        return ShareResult(**self._share_values(row, token=token), token=token)

    def _share_row(self, token, allow_preview=True):
        if not token:
            raise ValidationError("share token is required")
        row = self.repository.get_share_by_token_hash(self._token_hash(token))
        if row is None and allow_preview:
            share_id = self._preview_share_id(token)
            if share_id is not None:
                row = self.repository.get_share_by_id(share_id)
        if row is None:
            raise NotFoundError("share does not exist")
        return row

    def _preview_token(self, share_id):
        expires = int(datetime.now(timezone.utc).timestamp()) + self._PREVIEW_TTL_SECONDS
        payload = "{}.{}".format(share_id, expires)
        signature = hmac.new(
            self._preview_secret,
            payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        encoded = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        return "preview.{}.{}.{}".format(share_id, expires, encoded)

    def _preview_share_id(self, token):
        parts = token.split(".")
        if len(parts) != 4 or parts[0] != "preview":
            return None
        share_id, expires_text, supplied_signature = parts[1:]
        try:
            expires = int(expires_text)
        except ValueError:
            return None
        if expires < int(datetime.now(timezone.utc).timestamp()):
            return None
        payload = "{}.{}".format(share_id, expires_text)
        expected = hmac.new(
            self._preview_secret,
            payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        encoded = base64.urlsafe_b64encode(expected).decode("ascii").rstrip("=")
        return share_id if hmac.compare_digest(supplied_signature, encoded) else None

    def _share_info(self, row, token=None):
        return ShareInfo(**self._share_values(row, token=token))

    def _share_values(self, row, token=None):
        return {
            "share_id": row["share_id"],
            "artifact_id": row["artifact_id"],
            "artifact_version_id": row["artifact_version_id"],
            "version": row["version"],
            "name": row["name"],
            "source_session_id": row["source_session_id"],
            "source_path": row["source_path"],
            "mime_type": row["mime_type"],
            "storage_mode": row["storage_mode"],
            "storage_key": row["storage_key"],
            "size": row["size_bytes"],
            "checksum": row["checksum"],
            "visibility": row["visibility"],
            "permission": row["permission"],
            "created_by_id": row["share_created_by_id"],
            "created_by_name": row["share_created_by_name"],
            "expires_at": row["expires_at"],
            "revoked_at": row["revoked_at"],
            "created_at": row["share_created_at"],
            "url": self.base_url + "/s/" + token if token else None,
            # The durable link for the creator: rebuilt from the stored raw
            # token so an idempotent re-share can re-show the same URL.
            "share_url": (
                self.base_url + "/s/" + row["token"]
                if row["token"] and row["revoked_at"] is None
                else None
            ),
        }

    @staticmethod
    def _artifact_values(artifact):
        return {
            "artifact_id": artifact["artifact_id"],
            "source_session_id": artifact["source_session_id"],
            "source_path": artifact["source_path"],
            "name": artifact["name"],
            "artifact_type": artifact["artifact_type"],
            "dsh_workspace_id": artifact["dsh_workspace_id"],
            "dsh_workspace_path": artifact["dsh_workspace_path"],
            "dsh_workspace_title": artifact["dsh_workspace_title"],
            "created_by_id": artifact["created_by_id"],
            "created_by_name": artifact["created_by_name"],
            "created_at": artifact["created_at"],
            "status": artifact["status"],
        }

    @staticmethod
    def _id(prefix):
        return new_id(prefix)

    @staticmethod
    def _token_hash(token):
        return hash_token(token)

    @staticmethod
    def _now():
        return now_iso()

    @staticmethod
    def _mime_type(name):
        guessed = mimetypes.guess_type(name)[0]
        if guessed:
            return guessed
        common_types = {
            ".md": "text/markdown",
            ".csv": "text/csv",
            ".sql": "application/sql",
        }
        return common_types.get(Path(name).suffix.lower(), "application/octet-stream")

    @staticmethod
    def _validate_name(name):
        if not name or Path(name).name != name or name in (".", ".."):
            raise ValidationError("name must be a single safe file name")

    @staticmethod
    def _creator(created_by_id, created_by_name=None):
        if not isinstance(created_by_id, str) or not created_by_id.strip():
            raise ValidationError("created_by_id is required")
        created_by_id = created_by_id.strip()
        if len(created_by_id) > 128:
            raise ValidationError("created_by_id must not exceed 128 characters")
        # The creator ID is part of every artifact's relative storage key. Keep
        # it a single path component so it cannot escape the configured root.
        FilesystemStorage._validate_component(created_by_id, "created_by_id")
        if not isinstance(created_by_name, str) or not created_by_name.strip():
            created_by_name = created_by_id
        else:
            created_by_name = created_by_name.strip()
        if len(created_by_name) > 128:
            raise ValidationError("created_by_name must not exceed 128 characters")
        return created_by_id, created_by_name

    @staticmethod
    def _validate_workspace_metadata(workspace_id, workspace_path, workspace_title):
        limits = (
            ("dsh_workspace_id", workspace_id, 128),
            ("dsh_workspace_path", workspace_path, 512),
            ("dsh_workspace_title", workspace_title, 255),
        )
        for field, value, limit in limits:
            if value is not None and (not isinstance(value, str) or len(value) > limit):
                raise ValidationError(
                    "{} must be a string no longer than {} characters".format(
                        field, limit
                    )
                )

    @staticmethod
    def _validate_expiry(expires_at):
        if expires_at is not None:
            ArtifactHub._parse_time(expires_at)

    @staticmethod
    def _is_expired(expires_at):
        if expires_at is None:
            return False
        return ArtifactHub._parse_time(expires_at) <= datetime.now(timezone.utc)

    @staticmethod
    def _parse_time(value):
        return parse_iso(value)

    @staticmethod
    def _validate_share_options(visibility, permission):
        if visibility != "LINK":
            raise ValidationError("visibility must be LINK")
        if permission != "VIEW_DOWNLOAD":
            raise ValidationError("permission must be VIEW_DOWNLOAD")
