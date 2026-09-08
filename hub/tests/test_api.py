import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app
from artifact_hub.repositories.sqlite import SqliteArtifactRepository
from artifact_hub.services.artifact_hub import ArtifactHub


class ArtifactHubFastAPITests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.workspace = root / "workspace"
        self.workspace.mkdir()
        source = self.workspace / "report.md"
        source.write_text("# hello", encoding="utf-8")
        repository = SqliteArtifactRepository(root / "hub.sqlite3")
        self.hub = ArtifactHub(
            repository=repository,
            artifact_root=root / "artifacts",
            base_url="http://testserver",
        )
        self.client = TestClient(create_app(self.hub))

    def tearDown(self):
        self.hub.close()
        self.temp_dir.cleanup()

    def test_fastapi_local_share_metadata_content_and_listing(self):
        response = self.client.post(
            "/api/shares",
            json={
                "session_id": "sess-http",
                "workspace_root": str(self.workspace),
                "source_path": "report.md",
                "created_by_id": "user-http",
                "created_by_name": "HTTP User",
                "dsh_workspace_id": "workspace-http",
                "dsh_workspace_path": str(self.workspace.resolve()),
                "dsh_workspace_title": "HTTP Workspace",
            },
        )
        self.assertEqual(response.status_code, 201)
        created = response.json()["resultObj"]
        self.assertEqual(created["created_by_id"], "user-http")
        self.assertEqual(created["created_by_name"], "HTTP User")
        artifact = self.hub.repository.get_artifact(created["artifact_id"])
        self.assertEqual(artifact["dsh_workspace_id"], "workspace-http")
        self.assertEqual(artifact["dsh_workspace_title"], "HTTP Workspace")

        response = self.client.get("/s/{}".format(created["token"]))
        self.assertEqual(response.status_code, 200)
        metadata = response.json()["resultObj"]
        self.assertEqual(metadata["share_id"], created["share_id"])
        self.assertEqual(metadata["url"], created["url"])
        self.assertNotIn("token_hash", metadata)

        response = self.client.get("/s/{}/content".format(created["token"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"# hello")
        self.assertTrue(response.headers["content-type"].startswith("text/markdown"))

        response = self.client.get("/api/shares?created_by_id=user-http")
        self.assertEqual(response.status_code, 200)
        listed = response.json()["resultObj"]
        self.assertEqual(len(listed["items"]), 1)
        preview_url = listed["items"][0]["url"]
        self.assertTrue(preview_url.startswith("http://testserver/s/preview."))
        preview_token = preview_url.rsplit("/", 1)[-1]
        response = self.client.get("/api/public/shares/{}".format(preview_token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["resultObj"]["name"], "report.md")

    def test_local_share_reads_from_the_dsh_workspace_not_session_storage(self):
        workspace = Path(self.temp_dir.name) / "actual-dsh-workspace"
        workspace.mkdir()
        (workspace / "workspace-report.md").write_text(
            "# from workspace",
            encoding="utf-8",
        )

        response = self.client.post(
            "/api/shares",
            json={
                "session_id": "session-id-is-not-a-directory-name",
                "workspace_root": str(workspace),
                "source_path": "workspace-report.md",
                "created_by_id": "user-http",
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        token = response.json()["resultObj"]["token"]
        content = self.client.get("/api/public/shares/{}/content".format(token))
        self.assertEqual(content.content, b"# from workspace")

    def test_repeated_local_share_overwrites_the_version_share(self):
        request = {
            "session_id": "sess-http-overwrite",
            "workspace_root": str(self.workspace),
            "source_path": "report.md",
            "created_by_id": "user-http-overwrite",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
        first = self.client.post("/api/shares", json=request).json()["resultObj"]

        request["expires_at"] = None
        second = self.client.post("/api/shares", json=request).json()["resultObj"]

        self.assertEqual(second["share_id"], first["share_id"])
        self.assertEqual(second["artifact_version_id"], first["artifact_version_id"])
        self.assertNotEqual(second["token"], first["token"])
        self.assertIsNone(second["expires_at"])
        self.assertEqual(
            self.client.get("/api/public/shares/{}".format(first["token"])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/public/shares/{}".format(second["token"])).status_code,
            200,
        )
        listed = self.client.get(
            "/api/shares?created_by_id=user-http-overwrite"
        ).json()["resultObj"]
        self.assertEqual(len(listed["items"]), 1)

    def test_fastapi_validation_uses_shared_response_envelope(self):
        response = self.client.post("/api/shares", json={"source_path": "report.md"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["resultCode"], "422")
        self.assertEqual(response.json()["resultMsg"], "Request validation failed")

    def test_public_share_api_exposes_safe_metadata_preview_and_download(self):
        response = self.client.post(
            "/api/shares",
            json={
                "session_id": "sess-http",
                "workspace_root": str(self.workspace),
                "source_path": "report.md",
                "created_by_id": "user-http",
            },
        )
        token = response.json()["resultObj"]["token"]

        response = self.client.get("/api/public/shares/{}".format(token))
        self.assertEqual(response.status_code, 200)
        metadata = response.json()["resultObj"]
        self.assertEqual(metadata["name"], "report.md")
        self.assertEqual(metadata["permission"], "VIEW_DOWNLOAD")
        self.assertNotIn("storage_key", metadata)
        self.assertNotIn("checksum", metadata)
        self.assertEqual(response.headers["cache-control"], "private, no-store")

        response = self.client.get("/api/public/shares/{}/content".format(token))
        self.assertEqual(response.content, b"# hello")
        self.assertTrue(response.headers["content-disposition"].startswith("inline;"))
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

        response = self.client.get("/api/public/shares/{}/download".format(token))
        self.assertEqual(response.content, b"# hello")
        self.assertTrue(response.headers["content-disposition"].startswith("attachment;"))

    def test_unsupported_share_options_are_rejected(self):
        response = self.client.post(
            "/api/shares",
            json={
                "session_id": "sess-http",
                "workspace_root": str(self.workspace),
                "source_path": "report.md",
                "created_by_id": "user-http",
                "permission": "VIEW_ONLY",
            },
        )
        self.assertEqual(response.status_code, 422)

        response = self.client.post(
            "/api/shares",
            json={
                "session_id": "sess-http",
                "workspace_root": str(self.workspace),
                "source_path": "report.md",
                "created_by_id": "user-http",
                "visibility": "PRIVATE",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_public_share_errors_have_stable_codes_for_the_web_app(self):
        response = self.client.post(
            "/api/shares",
            json={
                "session_id": "sess-http",
                "workspace_root": str(self.workspace),
                "source_path": "report.md",
                "created_by_id": "user-http",
                "expires_at": "2000-01-01T00:00:00+00:00",
            },
        )
        token = response.json()["resultObj"]["token"]

        response = self.client.get("/api/public/shares/{}".format(token))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["resultObj"]["code"], "share_expired")


if __name__ == "__main__":
    unittest.main()
