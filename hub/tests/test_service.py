import hashlib
import tempfile
import unittest
import uuid
from pathlib import Path

from pydantic import BaseModel

from artifact_hub.domain.errors import HubError, ShareRevokedError
from artifact_hub.repositories.sqlite import SqliteArtifactRepository
from artifact_hub.services.artifact_hub import ArtifactHub


class ArtifactHubServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.workspace = root / "workspace"
        self.artifacts = root / "artifacts"
        self.workspace.mkdir()
        repository = SqliteArtifactRepository(root / "hub.sqlite3")
        self.hub = ArtifactHub(
            repository=repository,
            artifact_root=self.artifacts,
            base_url="https://share.example.test",
        )

    def tearDown(self):
        self.hub.close()
        self.temp_dir.cleanup()

    def test_local_share_is_an_immutable_snapshot(self):
        source = self.workspace / "report.html"
        source.write_text("first version", encoding="utf-8")

        result = self.hub.create_local_share(
            session_id="sess-1",
            workspace_root=self.workspace,
            source_path="report.html",
            created_by_id="user-1",
            created_by_name="User One",
            dsh_workspace_id="workspace-1",
            dsh_workspace_path=str(self.workspace.resolve()),
            dsh_workspace_title="Project One",
            artifact_type="html",
        )

        self.assertIsInstance(result, BaseModel)
        self.assertEqual(result.storage_mode, "LOCAL")
        self.assertEqual(result.size, len("first version"))
        self.assertEqual(
            result.checksum,
            hashlib.sha256(b"first version").hexdigest(),
        )
        self.assertTrue(result.url.startswith("https://share.example.test/s/"))
        self.assertEqual(str(uuid.UUID(result.artifact_id)), result.artifact_id)
        self.assertEqual(str(uuid.UUID(result.artifact_version_id)), result.artifact_version_id)
        self.assertEqual(str(uuid.UUID(result.share_id)), result.share_id)
        latest = self.hub.repository.get_latest_version(result.artifact_id)
        self.assertEqual(latest["created_by_id"], "user-1")
        self.assertEqual(latest["created_by_name"], "User One")
        artifact = self.hub.repository.get_artifact_by_source("sess-1", "report.html", "user-1")
        self.assertEqual(artifact["artifact_type"], "html")
        self.assertEqual(artifact["dsh_workspace_id"], "workspace-1")
        self.assertEqual(artifact["dsh_workspace_path"], str(self.workspace.resolve()))
        self.assertEqual(artifact["dsh_workspace_title"], "Project One")
        self.assertEqual(artifact["created_by_name"], "User One")
        snapshot = (
            self.artifacts
            / "user-1"
            / "artifacts"
            / result.artifact_id
            / "v1"
            / "report.html"
        )
        self.assertEqual(snapshot.read_text(encoding="utf-8"), "first version")

        source.write_text("changed later", encoding="utf-8")
        content = self.hub.read_share_content(result.token)
        self.assertEqual(content.body, b"first version")
        self.assertEqual(content.mime_type, "text/html")
        resolved = self.hub.resolve_share(result.token)
        self.assertEqual(resolved.url, result.url)

    def test_local_share_rejects_path_traversal(self):
        outside = Path(self.temp_dir.name) / "outside.txt"
        outside.write_text("not a session file", encoding="utf-8")

        with self.assertRaises(HubError):
            self.hub.create_local_share(
                session_id="sess-1",
                workspace_root=self.workspace,
                source_path="../../outside.txt",
                created_by_id="user-1",
            )

    def test_creator_id_must_be_safe_for_storage_path(self):
        source = self.workspace / "report.txt"
        source.write_text("content", encoding="utf-8")

        for created_by_id in ("../escape", "nested/user", r"nested\\user"):
            with self.subTest(created_by_id=created_by_id):
                with self.assertRaises(HubError):
                    self.hub.create_local_share(
                        session_id="sess-safe-id",
                        workspace_root=self.workspace,
                        source_path="report.txt",
                        created_by_id=created_by_id,
                    )

    def test_same_artifact_can_publish_a_new_version_without_changing_v1(self):
        source = self.workspace / "report.txt"
        source.write_text("v1", encoding="utf-8")
        first = self.hub.create_local_share(
            session_id="sess-versioned",
            workspace_root=self.workspace,
            source_path="report.txt",
            created_by_id="user-versioned",
        )

        source.write_text("v2", encoding="utf-8")
        second = self.hub.create_local_share(
            session_id="sess-versioned",
            workspace_root=self.workspace,
            source_path="report.txt",
            artifact_id=first.artifact_id,
            created_by_id="user-versioned",
        )

        self.assertEqual(second.version, 2)
        self.assertEqual(self.hub.read_share_content(first.token).body, b"v1")
        self.assertEqual(self.hub.read_share_content(second.token).body, b"v2")

    def test_repeated_share_of_unchanged_source_reuses_artifact_version(self):
        source = self.workspace / "stable.txt"
        source.write_text("same content", encoding="utf-8")

        first = self.hub.create_local_share(
            session_id="sess-stable",
            workspace_root=self.workspace,
            source_path="stable.txt",
            created_by_id="user-stable",
        )
        second = self.hub.create_local_share(
            session_id="sess-stable",
            workspace_root=self.workspace,
            source_path="stable.txt",
            created_by_id="user-stable",
        )

        self.assertEqual(second.artifact_id, first.artifact_id)
        self.assertEqual(second.artifact_version_id, first.artifact_version_id)
        self.assertEqual(second.version, first.version)
        self.assertEqual(second.share_id, first.share_id)
        self.assertEqual(second.token, first.token)
        self.assertEqual(second.url, first.url)
        self.assertEqual(second.created_at, first.created_at)
        self.assertEqual(self.hub.resolve_share(first.token).share_id, first.share_id)
        self.assertEqual(self.hub.resolve_share(second.token).share_id, first.share_id)
        self.assertEqual(
            len(self.hub.list_created_shares(created_by_id="user-stable")),
            1,
        )

        source.write_text("changed content", encoding="utf-8")
        third = self.hub.create_local_share(
            session_id="sess-stable",
            workspace_root=self.workspace,
            source_path="stable.txt",
            created_by_id="user-stable",
        )

        self.assertEqual(third.artifact_id, first.artifact_id)
        self.assertEqual(third.version, 2)
        self.assertNotEqual(third.artifact_version_id, first.artifact_version_id)
        self.assertNotEqual(third.token, second.token)
        self.assertEqual(self.hub.read_share_content(second.token).body, b"same content")
        self.assertEqual(self.hub.read_share_content(third.token).body, b"changed content")
        self.assertEqual(
            len(self.hub.list_created_shares(created_by_id="user-stable")),
            2,
        )

    def test_reshare_with_new_expiry_keeps_token_and_updates_expiry(self):
        source = self.workspace / "renewal.txt"
        source.write_text("renewal content", encoding="utf-8")

        first = self.hub.create_local_share(
            session_id="sess-renewal",
            workspace_root=self.workspace,
            source_path="renewal.txt",
            created_by_id="user-renewal",
        )
        self.assertIsNone(first.expires_at)

        second = self.hub.create_local_share(
            session_id="sess-renewal",
            workspace_root=self.workspace,
            source_path="renewal.txt",
            created_by_id="user-renewal",
            expires_at="2099-01-01T00:00:00+00:00",
        )

        self.assertEqual(second.token, first.token)
        self.assertEqual(second.share_id, first.share_id)
        self.assertEqual(second.expires_at, "2099-01-01T00:00:00+00:00")
        self.assertEqual(self.hub.resolve_share(first.token).share_id, first.share_id)
        row = self.hub.repository.get_share_by_version_id(first.artifact_version_id)
        self.assertEqual(row["token"], first.token)
        self.assertEqual(row["expires_at"], "2099-01-01T00:00:00+00:00")

    def test_reshare_after_revocation_rotates_token(self):
        source = self.workspace / "revoked.txt"
        source.write_text("revocation content", encoding="utf-8")

        first = self.hub.create_local_share(
            session_id="sess-revoked",
            workspace_root=self.workspace,
            source_path="revoked.txt",
            created_by_id="user-revoked",
        )
        self.hub.revoke_share(first.token, revoked_by_id="user-revoked")
        with self.assertRaises(ShareRevokedError):
            self.hub.resolve_share(first.token)

        second = self.hub.create_local_share(
            session_id="sess-revoked",
            workspace_root=self.workspace,
            source_path="revoked.txt",
            created_by_id="user-revoked",
        )

        self.assertEqual(second.share_id, first.share_id)
        self.assertNotEqual(second.token, first.token)
        # The rotated hash means the revoked link is gone entirely.
        with self.assertRaises(HubError):
            self.hub.resolve_share(first.token)
        self.assertEqual(self.hub.resolve_share(second.token).share_id, first.share_id)
        row = self.hub.repository.get_share_by_version_id(first.artifact_version_id)
        self.assertIsNone(row["revoked_at"])

    def test_reshare_of_expired_share_renews_same_token(self):
        source = self.workspace / "expired.txt"
        source.write_text("expired content", encoding="utf-8")

        first = self.hub.create_local_share(
            session_id="sess-expired",
            workspace_root=self.workspace,
            source_path="expired.txt",
            created_by_id="user-expired",
            expires_at="2000-01-01T00:00:00+00:00",
        )
        with self.assertRaises(HubError):
            self.hub.resolve_share(first.token)

        second = self.hub.create_local_share(
            session_id="sess-expired",
            workspace_root=self.workspace,
            source_path="expired.txt",
            created_by_id="user-expired",
            expires_at="2099-01-01T00:00:00+00:00",
        )

        self.assertEqual(second.token, first.token)
        self.assertEqual(self.hub.resolve_share(second.token).share_id, first.share_id)

    def test_reshare_of_legacy_row_without_token_mints_then_reuses(self):
        source = self.workspace / "legacy.txt"
        source.write_text("legacy content", encoding="utf-8")

        first = self.hub.create_local_share(
            session_id="sess-legacy",
            workspace_root=self.workspace,
            source_path="legacy.txt",
            created_by_id="user-legacy",
        )
        # Simulate a pre-migration row: hash only, no stored raw token.
        self.hub.repository.upsert_share(
            {
                "share_id": first.share_id,
                "artifact_version_id": first.artifact_version_id,
                "token_hash": hashlib.sha256(first.token.encode("utf-8")).hexdigest(),
                "token": None,
                "visibility": "LINK",
                "permission": "VIEW_DOWNLOAD",
                "expires_at": None,
                "revoked_at": None,
                "created_by_id": "user-legacy",
                "created_by_name": "user-legacy",
                "created_at": first.created_at,
                "updated_at": first.created_at,
            }
        )
        row = self.hub.repository.get_share_by_version_id(first.artifact_version_id)
        self.assertIsNone(row["token"])

        second = self.hub.create_local_share(
            session_id="sess-legacy",
            workspace_root=self.workspace,
            source_path="legacy.txt",
            created_by_id="user-legacy",
        )
        third = self.hub.create_local_share(
            session_id="sess-legacy",
            workspace_root=self.workspace,
            source_path="legacy.txt",
            created_by_id="user-legacy",
        )

        self.assertNotEqual(second.token, first.token)
        self.assertEqual(second.share_id, first.share_id)
        self.assertEqual(third.token, second.token)
        row = self.hub.repository.get_share_by_version_id(first.artifact_version_id)
        self.assertEqual(row["token"], second.token)

    def test_unchanged_explicit_artifact_reuses_latest_version(self):
        source = self.workspace / "explicit.txt"
        source.write_text("same content", encoding="utf-8")
        first = self.hub.create_local_share(
            session_id="sess-explicit",
            workspace_root=self.workspace,
            source_path="explicit.txt",
            created_by_id="user-explicit",
        )

        second = self.hub.create_local_share(
            session_id="sess-explicit",
            workspace_root=self.workspace,
            source_path="explicit.txt",
            artifact_id=first.artifact_id,
            created_by_id="user-explicit",
        )

        self.assertEqual(second.artifact_version_id, first.artifact_version_id)
        self.assertEqual(second.version, 1)

    def test_nas_prepare_and_commit_creates_share(self):
        prepared = self.hub.prepare_nas_share(
            session_id="sess-2",
            source_path="report.csv",
            created_by_id="user-2",
        )

        self.assertEqual(prepared.version, 1)
        self.assertEqual(str(uuid.UUID(prepared.upload_id)), prepared.upload_id)
        self.assertEqual(
            prepared.storage_key,
            "user-2/artifacts/{}/v1/report.csv".format(prepared.artifact_id),
        )
        target = Path(prepared.target_path)
        target.parent.mkdir(parents=True)
        target.write_text("a,b\n1,2\n", encoding="utf-8")

        result = self.hub.commit_nas_share(
            upload_id=prepared.upload_id,
            created_by_id="user-2",
            checksum=hashlib.sha256(b"a,b\n1,2\n").hexdigest(),
        )

        self.assertEqual(result.storage_mode, "NAS")
        self.assertEqual(self.hub.read_share_content(result.token).body, b"a,b\n1,2\n")
        latest = self.hub.repository.get_latest_version(result.artifact_id)
        self.assertEqual(latest["created_by_id"], "user-2")
        self.assertEqual(latest["created_by_name"], "user-2")

        with self.assertRaises(HubError):
            self.hub.commit_nas_share(upload_id=prepared.upload_id, created_by_id="user-2")

    def test_nas_commit_rejects_checksum_mismatch(self):
        prepared = self.hub.prepare_nas_share(
            session_id="sess-3",
            source_path="report.txt",
            created_by_id="user-3",
        )
        target = Path(prepared.target_path)
        target.parent.mkdir(parents=True)
        target.write_text("actual", encoding="utf-8")

        with self.assertRaises(HubError):
            self.hub.commit_nas_share(
                upload_id=prepared.upload_id,
                created_by_id="user-3",
                checksum="0" * 64,
            )

    def test_expired_and_revoked_shares_are_not_readable(self):
        source = self.workspace / "report.txt"
        source.write_text("content", encoding="utf-8")
        expired = self.hub.create_local_share(
            session_id="sess-4",
            workspace_root=self.workspace,
            source_path="report.txt",
            created_by_id="user-4",
            expires_at="2000-01-01T00:00:00+00:00",
        )
        with self.assertRaises(HubError):
            self.hub.resolve_share(expired.token)

        active = self.hub.create_local_share(
            session_id="sess-4",
            workspace_root=self.workspace,
            source_path="report.txt",
            created_by_id="user-4",
        )
        self.assertEqual(active.share_id, expired.share_id)
        self.hub.revoke_share(active.token, revoked_by_id="user-4")
        with self.assertRaises(HubError):
            self.hub.resolve_share(active.token)

    def test_future_expiry_is_persisted_and_share_remains_readable(self):
        source = self.workspace / "future.txt"
        source.write_text("content", encoding="utf-8")
        expires_at = "2099-12-31T16:00:00+00:00"

        result = self.hub.create_local_share(
            session_id="sess-future",
            workspace_root=self.workspace,
            source_path="future.txt",
            created_by_id="user-future",
            expires_at=expires_at,
        )

        self.assertEqual(result.expires_at, expires_at)
        self.assertEqual(self.hub.resolve_share(result.token).expires_at, expires_at)

    def test_creator_can_list_own_link_shares(self):
        source = self.workspace / "report.txt"
        source.write_text("content", encoding="utf-8")
        result = self.hub.create_local_share(
            session_id="sess-5",
            workspace_root=self.workspace,
            source_path="report.txt",
            created_by_id="user-5",
        )

        listed = self.hub.list_created_shares(created_by_id="user-5")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].share_id, result.share_id)
        self.assertEqual(listed[0].source_session_id, "sess-5")
        self.assertEqual(listed[0].source_path, "report.txt")
        self.assertTrue(listed[0].url.startswith("https://share.example.test/s/preview."))
        # The creator-facing durable link is rebuilt from the stored token.
        self.assertEqual(
            listed[0].share_url,
            "https://share.example.test/s/{}".format(result.token),
        )
        preview_token = listed[0].url.rsplit("/", 1)[-1]
        self.assertEqual(self.hub.resolve_share(preview_token).share_id, result.share_id)

        with self.assertRaises(HubError):
            self.hub.resolve_share(preview_token + "tampered")
        with self.assertRaises(HubError):
            self.hub.revoke_share(preview_token, revoked_by_id="user-5")

        self.assertEqual(self.hub.resolve_share(result.token).share_id, result.share_id)

        self.hub.revoke_share(result.token, revoked_by_id="user-5")
        revoked_listed = self.hub.list_created_shares(created_by_id="user-5")
        self.assertEqual(revoked_listed[0].revoked_at is not None, True)
        self.assertIsNone(revoked_listed[0].share_url)


if __name__ == "__main__":
    unittest.main()
