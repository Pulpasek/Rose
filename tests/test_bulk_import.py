import tempfile
import unittest
import zipfile
from pathlib import Path

from injection.mods.storage import ModStorageService


def make_zip(path: Path, member: str = "assets/game/data.txt"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(member, "hello")


class ModBulkImportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.storage = ModStorageService(
            mods_root=Path(self._tmp.name) / "mods"
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_import_mod_files_imports_multiple_archives(self):
        tmpdir = Path(self._tmp.name)
        a = tmpdir / "archive-a.zip"
        b = tmpdir / "archive-b.fantome"
        make_zip(a)
        make_zip(b)

        results = self.storage.import_mod_files(7, [a, b], [999])

        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["success"] for r in results))
        self.assertEqual(
            {r["modName"] for r in results},
            {"archive-a", "archive-b"},
        )

        mod_names = {m.mod_name for m in self.storage.list_mods_for_champion(7)}
        self.assertEqual(mod_names, {"archive-a", "archive-b"})

    def test_import_mod_files_duplicate_names_get_suffixed(self):
        tmpdir = Path(self._tmp.name)
        a = tmpdir / "same.zip"
        b = tmpdir / "placed-differently/same.zip"
        b.parent.mkdir(parents=True, exist_ok=True)
        make_zip(a)
        make_zip(b)

        results = self.storage.import_mod_files(7, [a, b], [999])

        self.assertTrue(all(r["success"] for r in results))
        mod_dirs = list(self.storage.get_champion_dir(7).iterdir())
        # Metadata file ignored; both archives extracted to distinct folders.
        folders = {p.name for p in mod_dirs if p.is_dir()}
        self.assertEqual(folders, {"same", "same (2)"})

    def test_import_mod_files_invalid_file_reports_error(self):
        tmpdir = Path(self._tmp.name)
        good = tmpdir / "good.zip"
        bad = tmpdir / "bad.txt"
        make_zip(good)
        bad.write_text("not a mod", encoding="utf-8")

        results = self.storage.import_mod_files(7, [good, bad], [999])

        self.assertTrue(results[0]["success"])
        self.assertFalse(results[1]["success"])
        self.assertIsNotNone(results[1]["error"])

    def test_import_category_mod_files_imports_multiple(self):
        tmpdir = Path(self._tmp.name)
        a = tmpdir / "font-a.zip"
        b = tmpdir / "font-b.zip"
        make_zip(a)
        make_zip(b)

        results = self.storage.import_category_mod_files("fonts", [a, b])

        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["success"] for r in results))
        self.assertEqual({r["modName"] for r in results}, {"font-a", "font-b"})

    def test_import_mod_files_empty_inputs(self):
        self.assertEqual(self.storage.import_mod_files(7, [], [999]), [])


if __name__ == "__main__":
    unittest.main()
