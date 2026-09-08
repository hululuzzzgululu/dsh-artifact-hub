import unittest
from pathlib import Path

from config.config_objects import HubConfig, StorageConfig
from config.manager import ConfigManager


class ConfigObjectTests(unittest.TestCase):
    def test_storage_defaults_to_sqlite(self):
        root = HubConfig()
        config = root.config

        self.assertEqual(config.storage.mode, "sqlite")
        self.assertEqual(config.storage.sqlite.path, Path("data/hub.sqlite3"))
        self.assertFalse(config.storage.uses_server)
        self.assertEqual(config.base_url, "http://127.0.0.1:8000")
        self.assertEqual(list(root.model_dump()), ["config"])

    def test_mysql_storage_is_nested_under_storage(self):
        config = ConfigManager(
            {
                "HUB_STORAGE_MODE": "mysql",
                "HUB_DATABASE_PATH": "/tmp/ignored.sqlite3",
                "HUB_MYSQL_HOST": "db.internal",
                "HUB_MYSQL_DATABASE": "artifact_hub",
                "HUB_MYSQL_POOL_SIZE": "8",
            }
        ).load().config

        self.assertEqual(config.storage.mode, "mysql")
        self.assertTrue(config.storage.uses_server)
        self.assertEqual(config.storage.server.host, "db.internal")
        self.assertEqual(config.storage.server.db, "artifact_hub")
        self.assertEqual(config.storage.server.pool_size, 8)
        self.assertEqual(config.storage.sqlite.path, Path("/tmp/ignored.sqlite3"))

    def test_datamind_server_mode_alias_uses_server_adapter(self):
        config = StorageConfig(mode="server")

        self.assertTrue(config.uses_server)


if __name__ == "__main__":
    unittest.main()
