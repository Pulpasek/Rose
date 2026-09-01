import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import config


class ConfigBehaviorTests(unittest.TestCase):
    def setUp(self):
        self._original_get_user_data_dir = config.get_user_data_dir
        self._tmp = TemporaryDirectory()
        config.get_user_data_dir = lambda: Path(self._tmp.name)
        config._CONFIG.clear()
        config._CONFIG_MTIME = 0.0

    def tearDown(self):
        config.get_user_data_dir = self._original_get_user_data_dir
        config._CONFIG.clear()
        config._CONFIG_MTIME = 0.0

    def test_set_config_option_updates_cached_config_immediately(self):
        config.set_config_option("General", "injection_threshold", "0.75")

        self.assertTrue(config._CONFIG.has_section("General"))
        self.assertEqual(config._CONFIG.get("General", "injection_threshold"), "0.75")
        self.assertEqual(config.get_config_option("General", "injection_threshold"), "0.75")


if __name__ == "__main__":
    unittest.main()
