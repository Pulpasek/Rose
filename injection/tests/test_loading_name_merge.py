import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from injection.loadingname import loading_name


class LoadingNameMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.game_dir = self.root / "game"
        self.mods_dir = self.root / "mods"
        self.mods_dir.mkdir()
        self.wad = self.game_dir / "Global.en_US.wad.client"

        self.game_texts = {
            "game_character_skin_displayname_Zed_1": "Shockblade Zed",
            "game_character_displayname_Zed": "Zed",
            "game_character_skin_displayname_Lux_1": "Elementalist Lux",
            "game_character_displayname_Lux": "Lux",
        }

    def skin_mod(self, alias):
        mod_folder = self.root / f"skin-{alias}"
        wad_dir = mod_folder / "WAD"
        wad_dir.mkdir(parents=True)
        (wad_dir / f"{alias}.wad.client").write_bytes(b"skin")
        return mod_folder

    def patch_game_data(self, overrides):
        texts_by_hash = {
            loading_name._key_hash(key): text
            for key, text in self.game_texts.items()
        }
        patches = [
            patch.object(loading_name, "_uses_string_overrides", return_value=overrides),
            patch.object(loading_name, "_language_wad", return_value=self.wad),
            patch.object(loading_name, "_read_table", return_value=b"RST\x05game-table"),
            patch.object(
                loading_name,
                "_text_of",
                side_effect=lambda _table, key_hash: texts_by_hash.get(key_hash),
            ),
            patch.object(loading_name, "_champion_record", return_value=None),
        ]
        return patches

    def test_string_overrides_accumulate_skin_names_for_multiple_champions(self):
        patches = self.patch_game_data(overrides=True)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            loading_name.build(
                self.game_dir, self.mods_dir, self.skin_mod("Zed"), 238001,
            )
            loading_name.build(
                self.game_dir, self.mods_dir, self.skin_mod("Lux"), 99001,
            )

        info = json.loads(
            (self.mods_dir / loading_name.MOD_FOLDER / "META" / "info.json").read_text(
                encoding="utf-8"
            )
        )
        texts = info["Layers"]["base"]["StringOverrides"]["en_us"]
        self.assertEqual(texts["game_character_displayname_Zed"], "Shockblade Zed")
        self.assertEqual(texts["game_character_displayname_Lux"], "Elementalist Lux")

    def test_localized_string_tables_accumulate_skin_names_for_multiple_champions(self):
        patches = self.patch_game_data(overrides=False)

        def append_text(table, key_hash, text):
            return table + b"|" + str(key_hash).encode() + b":" + text.encode()

        with patches[0], patches[1], patches[2], patches[3], patches[4], patch.object(
            loading_name, "_with_text", side_effect=append_text
        ):
            loading_name.build(
                self.game_dir, self.mods_dir, self.skin_mod("Zed"), 238001,
            )
            loading_name.build(
                self.game_dir, self.mods_dir, self.skin_mod("Lux"), 99001,
            )

        table = (
            self.mods_dir / loading_name.MOD_FOLDER / loading_name.TABLE_PATH
        ).read_bytes()
        self.assertIn(b"Shockblade Zed", table)
        self.assertIn(b"Elementalist Lux", table)


if __name__ == "__main__":
    unittest.main()
