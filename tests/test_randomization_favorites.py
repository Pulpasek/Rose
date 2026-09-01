import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from state.core.shared_state import SharedState
from ui.handlers.randomization_handler import RandomizationHandler
from utils.core import favorites as favorites_module


class RandomizationFavoritesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._old_get_user_data_dir = favorites_module.get_user_data_dir
        favorites_module.get_user_data_dir = lambda: Path(self._tmp.name)

    def tearDown(self):
        favorites_module.get_user_data_dir = self._old_get_user_data_dir
        self._tmp.cleanup()

    def test_shared_state_tracks_random_mode_type(self):
        state = SharedState()
        self.assertEqual(state.random_mode_type, "all")
        self.assertIsNone(state.random_chroma_id)

    def test_randomization_selects_skin_and_chroma(self):
        """Test that randomization selects both a skin and chroma"""
        state = SharedState()
        state.locked_champ_id = 42
        handler = RandomizationHandler(state, skin_scraper=None)

        class DummyCache:
            champion_id = 42
            skins = [
                {"skinId": 4200, "skinName": "Base"},
                {"skinId": 4201, "skinName": "Skin 1"},
                {"skinId": 4202, "skinName": "Skin 2"},
            ]
            chroma_id_map = {}

        class DummyScraper:
            cache = DummyCache()

            @staticmethod
            def get_chromas_for_skin(skin_id):
                # Return chromas for each skin (using 'id' key to match actual structure)
                if skin_id == 4201:
                    return [
                        {"id": 4201, "name": "Base"},
                        {"id": 4202, "name": "Chroma 1"},
                        {"id": 4203, "name": "Chroma 2"},
                    ]
                elif skin_id == 4202:
                    return [
                        {"id": 4202, "name": "Base"},
                        {"id": 4203, "name": "Chroma 1"},
                    ]
                return []

        handler.skin_scraper = DummyScraper()

        selection = handler.select_random_skin(mode="all")
        self.assertIsNotNone(selection)
        skin_name, skin_id, chroma_id = selection
        self.assertIn(skin_id, {4201, 4202})
        # Chroma should be either the base chroma (skin_id) or one of the chromas (skin_id + offset)
        self.assertIsNotNone(chroma_id)
        self.assertGreaterEqual(chroma_id, skin_id)
        self.assertLess(chroma_id, skin_id + 100)

    def test_randomization_uses_favorite_skins_and_chromas(self):
        """Test that favorites mode filters both skins and chromas"""
        state = SharedState()
        state.locked_champ_id = 42
        handler = RandomizationHandler(state, skin_scraper=None)

        favorites_module.save_favorites_data({
            "version": 1,
            "favorites": {
                "42": {
                    "skins": [4201, 4202],
                    "chromas": {
                        "4201": [4201, 4202],  # Favorite chromas for skin 4201
                        "4202": [4202]  # Favorite chromas for skin 4202
                    }
                }
            }
        })

        class DummyCache:
            champion_id = 42
            skins = [
                {"skinId": 4200, "skinName": "Base"},
                {"skinId": 4201, "skinName": "Fav 1"},
                {"skinId": 4202, "skinName": "Fav 2"},
                {"skinId": 4300, "skinName": "Other"},
            ]
            chroma_id_map = {}

        class DummyScraper:
            cache = DummyCache()

            @staticmethod
            def get_chromas_for_skin(skin_id):
                # Return chromas with 'id' key to match actual structure
                if skin_id == 4201:
                    return [
                        {"id": 4201, "name": "Base"},
                        {"id": 4202, "name": "Chroma 1"},
                        {"id": 4203, "name": "Chroma 2"},
                    ]
                elif skin_id == 4202:
                    return [
                        {"id": 4202, "name": "Base"},
                        {"id": 4203, "name": "Chroma 1"},
                    ]
                return []

        handler.skin_scraper = DummyScraper()

        selection = handler.select_random_skin(mode="favorites")
        self.assertIsNotNone(selection)
        skin_name, skin_id, chroma_id = selection
        # Should be one of the favorite skins
        self.assertIn(skin_id, {4201, 4202})
        # Should be one of the favorite chromas for this skin
        if skin_id == 4201:
            self.assertIn(chroma_id, {4201, 4202})
        elif skin_id == 4202:
            self.assertIn(chroma_id, {4202})

    def test_force_base_skin_marks_random_mode_before_transition(self):
        state = SharedState()
        state.locked_champ_id = 42
        handler = RandomizationHandler(state, skin_scraper=None)

        class DummyLCU:
            def __init__(self):
                self.called_with = None

            def set_my_selection_skin(self, skin_id):
                self.called_with = skin_id
                return True

        lcu = DummyLCU()
        captures = {}

        def fake_start(mode):
            captures["mode"] = mode
            captures["random_active"] = state.random_mode_active
            captures["random_type"] = state.random_mode_type

        handler._start_randomization = fake_start

        result = handler.force_base_skin_and_randomize(lcu, mode="favorites")

        self.assertTrue(result)
        self.assertTrue(state.random_mode_active)
        self.assertEqual(state.random_mode_type, "favorites")
        self.assertEqual(lcu.called_with, 42000)
        self.assertEqual(captures["mode"], "favorites")
        self.assertTrue(captures["random_active"])


if __name__ == "__main__":
    unittest.main()
