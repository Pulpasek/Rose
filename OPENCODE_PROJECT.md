# Rose — OpenCode Project Documentation

This document explains the overall architecture of the **Rose** project: a League of
Legends modding tool that mixes a Python application (injection, monitoring, party
mode, settings) with JavaScript plugins that run inside **Pengu Loader** (the in-client
COM/toolkit that unlocks the champion-select UI).

> Audience: an AI agent (or developer) working on this repo. It maps every major
> directory, explains the JS ↔ Python communication bridge, the on-disk mod layout,
> the testing approach, and the most commonly edited files.

---

## 1. High-level picture

```
    League of Legends client (champion select UI)
            ▲                          ▲
            │  in-client UI            │
   JavaScript plugins (Pengu Loader)   │
   ┌───────────────────────────────────┐
   │  ROSE-SkinMonitor  (the bridge)   │
   │  ROSE-UI, ROSE-ChromaWheel, ...   │  <- one per feature
   └───────────────▲───────────────────┘
                   │  WebSocket (JSON)
                   │  https://127.0.0.1:<port>
   ┌───────────────┴───────────────────┐
   │  pengu/  Python bridge server     │  HTTP + WebSocket server (port 50000+)
   └───────────────▲───────────────────┘
                   │
   ┌───────────────┴───────────────────┐
   │  injection/  mod storage &       │  reads/writes %LOCALAPPDATA%\Rose\mods
   │              DLL injection       │
   └──────────────────────────────────┘
```

- **Python** owns the game-session state, mod storage/import/export, random skin
  selection, favorites, party mode, and the HTTP/WebSocket server.
- **JavaScript** (Pengu Loader plugins) owns the in-client UI. It asks Python for data
  and receives responses over a WebSocket bridge.
- Mods live on disk under `%LOCALAPPDATA%\Rose\mods` and are injected into the game
  with a DLL (`cslol-dll.dll`) plus `mod-tools.exe`.

---

## 2. Top-level directories

| Path | Purpose |
|---|---|
| `main.py` | Minimal entry point: adds repo root to `sys.path`, calls `main()` from `main/__init__.py`. |
| `main/` | App orchestration. `main/__init__.py:main()` checks `cslol-dll.dll`, runs the auto-updater `launcher`, then `run_league_unlock()`. Subpackages: `setup/`, `core/` (signals, single-instance lock, cleanup), `runtime/loop.py` (main event loop). |
| `config.py` | Central constants (`APP_VERSION`), polling intervals, timeouts, and `config.ini` helpers. |
| `pengu/` | **The JS↔Python bridge.** `pengu/core/` (WebSocket server, HTTP handler, skin monitor thread), `pengu/communication/` (message handler + broadcaster), `pengu/processing/` (skin-name→ID resolution). |
| `injection/` | Mod subsystem. `injection/mods/` (`ModStorageService`, `ModManager`, `ZipResolver`), `injection/core/` (`InjectionManager`, `SkinInjector`), `injection/config/`, `injection/overlay/`, `injection/game/`, `injection/tools/` (ships `mod-tools.exe`), `injection/mods_map.json`. |
| `lcu/` | League Client Update (LCU) API layer — HTTP client, connection/lockfile, skin cache & scraper, skin selection features. |
| `party/` | Party Mode — P2P skin sharing. Groups my friends through a WebSocket relay (`relay-worker/`), UDP transport, STUN, lobby room derivation. |
| `state/` | Shared app state. `state/core/shared_state.py` (`SharedState` dataclass) + `app_status.py`. |
| `ui/` | UI logic: `ui/core/`, `ui/chroma/` (chroma panel/preview), `ui/handlers/` (randomization). |
| `utils/` | Shared utilities: paths, logging, favorites, custom-skin favorites, junction/symlink, security/CORS, safe extraction, issue reporter. |
| `threads/` | Background threads: phase monitoring, champion detection, LCU monitoring, WebSocket communication. |
| `analytics/` | Optional usage analytics (`AnalyticsClient`, machine/install IDs). |
| `launcher/` | Auto-updater (`updater.py`, `launcher/core/`, `launcher/update/`, `launcher/ui/`). |
| `relay-worker/` | Cloudflare Workers (Durable Object) WebSocket relay used by Party Mode. TypeScript. |
| `vendor/` | Vendored Pengu Loader source (`vendor/PenguLoader-1.1.6/`), compiled during packaging. |
| `assets/` | Icons, tray buttons, fonts (`BeaufortforLOL-*`), sound effects. |
| `Pengu Loader/` | Bundled runtime: `Pengu Loader.exe`, `core.dll`, `plugins/`, `config/`, `datastore/`. |
| `build/` / `dist/` | Build intermediates / packaged output. |
| `test/` | Legacy supplementary tests (`test_pengu_loader.py`). |
| `tests/` | **Primary unittest suite** (see §6). |
| `scripts/` | Build scripts: `build_all.py`, `build_pengu_loader.py`, `build_pyinstaller.py`, `create_installer.py`. |
| `installer/` | Pre-built `Rose_Setup.exe` (Inno Setup); `installer.iss` is the script. |

---

## 3. The JS ↔ Python bridge (most important concept)

The JavaScript plugins talk to Python over a **WebSocket** carrying JSON messages.

### Discovery
- `pengu/core/skin_monitor.py` (`PenguSkinMonitorThread`) starts a combined
  **HTTP + WebSocket server** on a free port (default 50000) and writes that port to
  `%LOCALAPPDATA%\Rose\state\bridge_port.txt`.
- **ROSE-SkinMonitor** (the core bridge plugin) discovers the port (via local cache,
  then ports 50000/50001, then a scan), then opens the WebSocket.

### The bridge object
- **ROSE-SkinMonitor** exposes `window.__roseBridge` (and `window.__roseBridgeEmit`).
- Other plugins call `waitForBridge()` to wait until it appears (10 s timeout), then
  `bridge.send({...})` to send JSON to Python.
- **Subscriptions:** `bridge.subscribe(type, cb)` / `unsubscribe(type, cb)`. Inbound
  messages are dispatched by `type`. `ROSE-SkinMonitor` also re-dispatches several
  responses as `CustomEvent`s (e.g. `rose-custom-wheel-skin-mods`,
  `lu-skin-monitor-state`).

### Common message types
- **Outbound (JS → Python):** `skin`/`skin-sync`, `chroma-selection`,
  `dice-button-click`, `favorite-toggle-skin`/`-chroma`, `request-favorites`,
  `request-skin-mods`, `select-skin-mod`, `add-custom-mods-*`, `delete-*-mod`,
  `rename-*-mod`, `request-maps`/`fonts`/`announcers`, `set-mod-image`, and the
  **export** messages (`export-skin-mods`, `export-category-mods`).
- **Inbound (Python → JS):** `skin-state`, `skin-mods-response`,
  `maps-response`, `fonts-response`, `announcers-response`, `category-mods-response`,
  `mod-image-set`, **`skin-mods-exported`**, **`category-mods-exported`**,
  `settings-data`, `diagnostics-data`, `favorites-state`, `manage-favorites-data`,
  `champion-locked`, `phase-change`, `party-state`.

Routing for these messages lives in `pengu/communication/message_handler.py`
(`MessageHandler`). New message types: add a branch there, plus a `broadcast`/`send`
call in `pengu/communication/broadcaster.py`, plus a `bridge.subscribe` in the relevant
plugin's `index.js`.

---

## 4. Plugins (`Pengu Loader/plugins/`)

| Plugin | Purpose |
|---|---|
| **ROSE-SkinMonitor** | Core bridge: connects to Python, polls the DOM for hovered skins, sends `skin` events, re-dispatches responses as `CustomEvent`s. |
| **ROSE-UI** | Interface unlocker — makes locked skins visible/previewable. |
| **ROSE-ChromaWheel** | Chroma radial wheel for champion select. |
| **ROSE-CustomWheel** | Radial wheel that lists installed custom mods for a hovered skin. |
| **ROSE-CustomSkinSelector** | Button + flyout to list/select/import mods for the current skin. |
| **ROSE-RandomSkin** | Random skin / favorites roll. |
| **ROSE-Favorites** | Star favorites for skins & chromas. |
| **ROSE-SettingsPanel** | Settings UI — thresholds, paths, diagnostics, **manage mods** (import/delete/rename/export). |
| **ROSE-PartyMode** | Party Mode UI (skin sharing). |
| **ROSE-HistoricMode** | Shows previously-used ("historic") mods. |
| **ROSE-FormsWheel** | Custom wheel for skins with "forms" (Sahn Uzal, Legend Kai'Sa/Ahri). |
| **ROSE-Jade** | Regalia (player-card) customization. Currently disabled (`index.js_`). |

---

## 5. On-disk mod structure

Root mods directory: `%LOCALAPPDATA%\Rose\mods`, auto-enforced to the following
categories: `skins`, `maps`, `fonts`, `announcers`, `ui`, `voiceover`,
`loading_screen`, `vfx`, `sfx`, `others`.

### Champion (skin) mods
```
mods/skins/{champion_id * 1000}/{mod_folder_name}/
```
Example: Garen (champion ID 7) → `mods/skins/7000/`.

Each mod folder:
```
{mod_folder_name}/
  META/image.png            # custom thumbnail (from set-mod-image)
  display_name.txt          # optional display alias
  description.txt           # optional description
  assets/game/...           # WAD / mod data
```

Manifest (in the champion dir, not each mod): `rose_mod_targets.json`
```json
{
  "version": 1,
  "championId": 7,
  "targets": [7000],
  "mods": {
    "<folderHash>": {
      "name": "ModFolder",
      "displayName": "Nice Skin",
      "wadHashes": { "assets/game/data.wad": "..." },
      "targets": [7000, 7001]
    }
  }
}
```

### Category mods
```
mods/{category}/{mod_folder_name}/
```
Each category dir has `rose_category_mods.json`:
```json
{
  "version": 1,
  "category": "maps",
  "mods": {
    "ModName": { "name": "ModName", "path": "ModName", "displayName": "..." }
  }
}
```

### Import / Export
- **Import:** `import_mod_files` accepts multiple `.zip`/`.fantome` archives + champion
  ID + target skins. Each archive is extracted independently; duplicates get suffixes
  (`same`, `same (2)`, …); MAX_PATH is handled by truncating folder names.
- **Export:** `export_champion_mods(entries, dest, fmt)` and
  `export_category_mods(category, names, dest, fmt)` produce `.fantome` (default) or
  `.zip` archives named after the mod's `display_name` (sanitized; fallback to folder
  name), with filename dedup. The folder destination is chosen each time with a native
  folder picker.

---

## 6. Testing

Framework: Python's built-in **unittest** (no pytest).

Primary suite in `tests/`:
- `test_export_mods.py` — champion/category export, archive naming, dedupe, bulk, errors.
- `test_bulk_import.py` — bulk import, duplicate suffixing, invalid files.
- `test_mod_image_behavior.py` — setting a custom mod image.
- `test_config_behavior.py` — `config.py` caching.
- `test_randomization_favorites.py` — `RandomizationHandler` (note: one randomization
  test is flaky — it may return the base skin and fail intermittently).
- `test_party_reliability.py` — party room keys, relay reconnection, peer removal.

Other suites:
- `test/test_pengu_loader.py` — Pengu Loader CLI activation/deactivation.
- `analytics/tests/test_analytics.py` — analytics.

Commands:
```powershell
python -m unittest discover -s tests        # primary suite
python -m unittest test.test_pengu_loader    # legacy Penul loader tests
python -m unittest analytics.tests.test_analytics
```

Syntax checks:
```powershell
python -m py_compile <file.py>                          # Python
node --check "Pengu Loader/plugins/ROSE-*/index.js"     # JavaScript
```

---

## 7. Commonly touched files (FAQs)

- `config.py` — add/tune constants that drive app behavior.
- `pengu/communication/message_handler.py` — add/handle new WebSocket message types.
- `pengu/communication/broadcaster.py` — send new outbound message types to JS.
- `injection/mods/storage.py` — mod storage hierarchy, import/export, display names,
  `set_mod_image`.
- `Pengu Loader/plugins/ROSE-SkinMonitor/index.js` — the JS bridge, port discovery,
  the subscribe/send API, `CustomEvent` re-dispatch.
- Individual `Pengu Loader/plugins/ROSE-*/index.js` — per-feature UI.
- `tests/` — add new test cases.
- `Rose.spec`, `requirements.txt`, `scripts/*.py`, `installer.iss` — packaging/build.

---

## 8. Build & packaging (brief)

- `scripts/build_pengu_loader.py` compiles vendored Pengu Loader from `vendor/`.
- `scripts/build_pyinstaller.py` packages Python via PyInstaller (`Rose.spec`, `requirements.txt`).
- `scripts/create_installer.py` + `installer.iss` build the Inno Setup `Rose_Setup.exe`.
- `scripts/build_all.py` runs the whole pipeline.
- Requires Python ≥ 3.11; deps: psutil, requests, websocket-client, websockets, Pillow,
  pystray, pyinstaller.
