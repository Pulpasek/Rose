#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Custom Skin Favorites Manager
Persists the "favorite champions" and "favorite skins" data used by the
Manage list / Add Custom Skin dialog of the Settings Panel.

Unlike the in-game favorites (utils/core/favorites.py), these favorites were
originally stored in the League client's in-page localStorage, which is wiped
every time the client restarts. Persisting them to disk prevents that reset.

Saved in %LOCALAPPDATA%\\Rose\\custom_skin_favorites.json.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List

from utils.core.paths import get_user_data_dir

log = logging.getLogger(__name__)

_favorites_lock = threading.Lock()


def _get_favorites_file_path() -> Path:
    """Return the Path to custom_skin_favorites.json in the user data directory."""
    data_dir = get_user_data_dir()
    return data_dir / "custom_skin_favorites.json"


def _default_data() -> Dict[str, Any]:
    """Return the default favorites structure."""
    return {"version": 1, "favoriteChampions": [], "favoriteSkins": {}}


def load() -> Dict[str, Any]:
    """Load the full custom skin favorites dictionary. Returns default on error/missing."""
    with _favorites_lock:
        path = _get_favorites_file_path()
        if not path.exists():
            return _default_data()

        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return _default_data()
            if "favoriteChampions" not in data or "favoriteSkins" not in data:
                return _default_data()
            return data
        except Exception as e:
            log.warning(f"[CustomSkinFavorites] Failed to load custom_skin_favorites.json: {e}")
            return _default_data()


def save(data: Dict[str, Any]) -> bool:
    """Save the full favorites data dictionary to custom_skin_favorites.json."""
    with _favorites_lock:
        path = _get_favorites_file_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            log.error(f"[CustomSkinFavorites] Failed to save custom_skin_favorites.json: {e}")
            return False


def _normalise_positive_ids(ids: Any) -> List[int]:
    """Return a sorted list of positive ints from an arbitrary value."""
    out = []
    if isinstance(ids, (list, set)):
        for item in ids:
            try:
                num = int(item)
            except (ValueError, TypeError):
                continue
            if num > 0 and num not in out:
                out.append(num)
    return sorted(out)


def _normalise_skin_map(skins: Any) -> Dict[str, List[int]]:
    """Return a dict of {championId: [skinIds]} with positive int values."""
    result: Dict[str, List[int]] = {}
    if isinstance(skins, dict):
        for champ_key, skin_ids in skins.items():
            ids = _normalise_positive_ids(skin_ids)
            if ids:
                result[str(champ_key)] = ids
    return result


def get_favorite_champions() -> List[int]:
    """Get the list of favorited champion IDs."""
    data = load()
    return _normalise_positive_ids(data.get("favoriteChampions", []))


def toggle_champion_favorite(champion_id: int) -> List[int]:
    """Toggle favorite status for a champion. Returns the updated champion ID list."""
    data = load()
    champions = _normalise_positive_ids(data.get("favoriteChampions", []))
    champion_num = int(champion_id)

    if champion_num in champions:
        champions.remove(champion_num)
        log.info(f"[CustomSkinFavorites] Removed champion {champion_num} from favorites")
    else:
        champions.append(champion_num)
        log.info(f"[CustomSkinFavorites] Added champion {champion_num} to favorites")

    data["favoriteChampions"] = sorted(champions)
    save(data)
    return data["favoriteChampions"]


def get_favorite_skins(champion_id: int) -> List[int]:
    """Get the list of favorited skin IDs for a champion."""
    data = load()
    skins_map = _normalise_skin_map(data.get("favoriteSkins", {}))
    return skins_map.get(str(int(champion_id)), [])


def toggle_skin_favorite(champion_id: int, skin_id: int) -> Dict[str, List[int]]:
    """Toggle favorite status for a skin. Returns the updated skin map."""
    data = load()
    skins_map = _normalise_skin_map(data.get("favoriteSkins", {}))
    champ_key = str(int(champion_id))
    skin_num = int(skin_id)

    champ_skins = skins_map.setdefault(champ_key, [])
    if skin_num in champ_skins:
        champ_skins.remove(skin_num)
        log.info(f"[CustomSkinFavorites] Removed skin {skin_num} for champion {champion_id}")
    else:
        champ_skins.append(skin_num)
        log.info(f"[CustomSkinFavorites] Added skin {skin_num} for champion {champion_id}")

    if champ_skins:
        skins_map[champ_key] = sorted(champ_skins)
    else:
        skins_map.pop(champ_key, None)

    data["favoriteSkins"] = skins_map
    save(data)
    return data["favoriteSkins"]


def to_dict() -> Dict[str, Any]:
    """Return the full normalised favorites structure for the JS UI."""
    data = load()
    return {
        "version": 1,
        "favoriteChampions": _normalise_positive_ids(data.get("favoriteChampions", [])),
        "favoriteSkins": _normalise_skin_map(data.get("favoriteSkins", {})),
    }
