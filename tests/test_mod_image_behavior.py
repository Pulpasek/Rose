import base64
import tempfile
import unittest
from pathlib import Path

from injection.mods.storage import ModStorageService


class ModImageBehaviorTests(unittest.TestCase):
    def test_set_mod_image_creates_meta_image_and_is_visible_in_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = ModStorageService(mods_root=Path(tmpdir) / "mods")
            champion_dir = storage.get_champion_dir(1)
            mod_dir = champion_dir / "My Custom Mod"
            mod_dir.mkdir(parents=True, exist_ok=True)
            storage.set_champion_target_ids(
                champion_id=1,
                skin_ids=[1],
                mod_name="My Custom Mod",
                mod_path=mod_dir,
            )

            storage.set_mod_image(
                champion_id=1,
                mod_name="My Custom Mod",
                relative_path=None,
                image_data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAF",
                mime_type="image/png",
            )

            meta_image = mod_dir / "META" / "image.png"
            self.assertTrue(meta_image.exists())
            self.assertEqual(storage.list_mods_for_champion(1)[0].mod_name, "My Custom Mod")

            payload = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAF")
            self.assertTrue(meta_image.read_bytes().startswith(payload[:8]))


if __name__ == "__main__":
    unittest.main()
