import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO, Tuple

from ..domain.errors import ValidationError


class FilesystemStorage:
    """Filesystem adapter for immutable Artifact Version files."""

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def source_path(self, workspace_root, source_path):
        workspace_root = Path(workspace_root).expanduser()
        if not workspace_root.is_absolute():
            raise ValidationError("workspace_root must be absolute")
        workspace_root = workspace_root.resolve()
        relative = self.validate_source_path(source_path)
        candidate = workspace_root / relative
        return self._inside(candidate, workspace_root, "source_path")

    @staticmethod
    def validate_source_path(source_path):
        relative = Path(source_path)
        if relative.is_absolute():
            raise ValidationError("source_path must be relative to the workspace")
        if ".." in relative.parts:
            raise ValidationError("source_path escapes the workspace")
        return relative

    def storage_key(self, artifact_id, version, name):
        self._validate_component(artifact_id, "artifact_id")
        self._validate_component(name, "name")
        if version < 1:
            raise ValidationError("version must be positive")
        return "artifacts/{}/v{}/{}".format(artifact_id, version, name)

    def target_path(self, storage_key):
        candidate = self.root / Path(storage_key)
        return self._inside(candidate, self.root, "storage_key")

    def copy_snapshot(self, source, storage_key):
        source = Path(source)
        if not source.is_file():
            raise ValidationError("source Session File does not exist")
        destination = self.target_path(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=".artifact-", suffix=".tmp", dir=str(destination.parent)
        )
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            shutil.copyfile(str(source), str(temporary))
            os.replace(str(temporary), str(destination))
        finally:
            if temporary.exists():
                temporary.unlink()
        return destination

    def inspect(self, storage_key) -> Tuple[int, str]:
        path = self.target_path(storage_key)
        if not path.is_file():
            raise ValidationError("prepared Artifact Version file does not exist")
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
        return size, digest.hexdigest()

    def open(self, storage_key) -> BinaryIO:
        path = self.target_path(storage_key)
        if not path.is_file():
            raise ValidationError("Artifact Version file does not exist")
        return path.open("rb")

    def discard(self, storage_key):
        """Remove an unpublished snapshot and its empty version directory."""
        path = self.target_path(storage_key)
        if path.exists():
            path.unlink()
        parent = path.parent
        while parent != self.root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    @staticmethod
    def _validate_component(value, label):
        if (
            not value
            or Path(value).name != value
            or value in (".", "..")
            or any(character in value for character in ("\r", "\n"))
        ):
            raise ValidationError("{} must be a single safe path component".format(label))

    @staticmethod
    def _inside(candidate, root, label):
        resolved = Path(candidate).expanduser().resolve()
        root = Path(root).expanduser().resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            raise ValidationError("{} escapes its configured root".format(label))
        return resolved
