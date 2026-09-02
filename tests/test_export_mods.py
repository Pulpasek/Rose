import tempfile
import unittest
import zipfile
from pathlib import Path

from injection.mods.storage import ModStorageService, SkinModEntry


def make_mod_folder(base: Path, name: str, display_name: str = None, with_meta: bool = True):
    """Create a mod folder with a nested asset, optional META/image.png and description."""
    mod_dir = base / name
    (mod_dir / "assets" / "game").mkdir(parents=True, exist_ok=True)
    (mod_dir / "assets" / "game" / "data.bin").write_bytes(b"SKIN-DATA")
    if with_meta:
        meta = mod_dir / "META"
        meta.mkdir(parents=True, exist_ok=True)
        (meta / "image.png").write_bytes(b"\x89PNG-fake")
    (mod_dir / "description.txt").write_text("hello", encoding="utf-8")
    if display_name is not None:
        (mod_dir / "display_name.txt").write_text(display_name, encoding="utf-8")
    return mod_dir


def read_zip_entries(path: Path):
    with zipfile.ZipFile(path, "r") as zf:
        return sorted(zf.namelist()), {n: zf.read(n) for n in zf.namelist()}


class ModExportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.storage = ModStorageService(mods_root=self.tmp / "mods")
        self.out = self.tmp / "exports"
        self.out.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_export_champion_mod_creates_archive_named_after_display_name(self):
        mod_dir = make_mod_folder(self.storage.get_champion_dir(7), "InternalFolder", display_name="Nice Skin")
        entry = SkinModEntry(
            champion_id=7, skin_id=7000, mod_name="InternalFolder",
            path=mod_dir, updated_at=0.0, display_name="Nice Skin",
        )
        out_path, file_name = self.storage.export_champion_mod(entry, self.out, "fantome")
        self.assertTrue(out_path.exists())
        self.assertEqual(out_path.name, "Nice Skin.fantome")
        names, contents = read_zip_entries(out_path)
        self.assertIn("assets/game/data.bin", names)
        self.assertIn("META/image.png", names)
        self.assertIn("description.txt", names)
        self.assertEqual(contents["assets/game/data.bin"], b"SKIN-DATA")

    def test_export_zip_and_fantome_have_same_content(self):
        mod_dir = make_mod_folder(self.storage.get_champion_dir(7), "Mod")
        entry = SkinModEntry(
            champion_id=7, skin_id=7000, mod_name="Mod",
            path=mod_dir, updated_at=0.0, display_name="Same",
        )
        z_path, z_name = self.storage.export_champion_mod(entry, self.out, "zip")
        f_path, f_name = self.storage.export_champion_mod(entry, self.out, "fantome")
        self.assertEqual(z_name, "Same.zip")
        self.assertEqual(f_name, "Same.fantome")
        z_names, z_contents = read_zip_entries(z_path)
        f_names, f_contents = read_zip_entries(f_path)
        self.assertEqual(z_names, f_names)
        self.assertEqual(z_contents, f_contents)

    def test_sanitize_export_filename_strips_invalid_chars(self):
        self.assertEqual(
            ModStorageService._sanitize_export_filename('A/B:C"D<E>F|G?H\\I'),
            "ABCDEFGHI",
        )
        self.assertEqual(
            ModStorageService._sanitize_export_filename("trailing dot."),
            "trailing dot",
        )
        self.assertEqual(ModStorageService._sanitize_export_filename(""), "mod")
        self.assertEqual(ModStorageService._sanitize_export_filename(None), "mod")

    def test_export_champion_mods_bulk(self):
        mods = []
        for i, nm in enumerate(["ModA", "ModB"]):
            mod_dir = make_mod_folder(self.storage.get_champion_dir(7), nm, display_name=f"Skin {i}")
            mods.append(SkinModEntry(
                champion_id=7, skin_id=7000, mod_name=nm, path=mod_dir,
                updated_at=0.0, display_name=f"Skin {i}",
            ))
        results = self.storage.export_champion_mods(mods, self.out, "zip")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["success"] for r in results))
        self.assertEqual({Path(r["filePath"]).name for r in results}, {"Skin 0.zip", "Skin 1.zip"})

    def test_export_category_mods_bulk(self):
        cat = "maps"
        (self.storage.mods_root / cat).mkdir(parents=True, exist_ok=True)
        make_mod_folder(self.storage.mods_root / cat, "MapA", display_name=None)
        make_mod_folder(self.storage.mods_root / cat, "MapB", display_name=None)
        results = self.storage.export_category_mods(cat, ["MapA", "MapB"], self.out, "fantome")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["success"] for r in results))
        self.assertEqual(
            {Path(r["filePath"]).name for r in results},
            {"MapA.fantome", "MapB.fantome"},
        )

    def test_export_missing_folder_reports_error(self):
        entry = SkinModEntry(
            champion_id=7, skin_id=7000, mod_name="Missing",
            path=self.tmp / "does_not_exist", updated_at=0.0, display_name="Missing",
        )
        results = self.storage.export_champion_mods([entry], self.out, "zip")
        self.assertFalse(results[0]["success"])
        self.assertIsNotNone(results[0]["error"])

    def test_export_dedupe_existing_file(self):
        mod_dir = make_mod_folder(self.storage.get_champion_dir(7), "Mod", display_name="Dup")
        entry = SkinModEntry(
            champion_id=7, skin_id=7000, mod_name="Mod",
            path=mod_dir, updated_at=0.0, display_name="Dup",
        )
        first, _ = self.storage.export_champion_mod(entry, self.out, "zip")
        second, name2 = self.storage.export_champion_mod(entry, self.out, "zip")
        self.assertEqual(first.name, "Dup.zip")
        self.assertEqual(name2, "Dup (2).zip")


if __name__ == "__main__":
    unittest.main()
