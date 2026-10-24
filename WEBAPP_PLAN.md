# img2print web app: plan and progress

A browser app for img2print. You drop in a logo (PNG/JPG/SVG/PDF), tune the settings with a live 2D/3D preview, and download the 3MF and STL files.

**Decisions:**
- Local first, deployable later. It runs on the PC with one command, and a Docker image is for hosting later. There are no accounts and no database.
- The frontend is React + Vite + TypeScript + three.js (react-three-fiber), built to static files that the Python backend serves.
- Develop this project on a local disk, not on Google Drive. Drive's `G:` drive can't hold `node_modules` sensibly: it allows no junctions or symlinks, and it would sync about 30k files.

```
browser (React SPA) ──JSON + upload──► FastAPI (img2print.web) ──► img2print library
  3D preview ◄── GLB    downloads ◄── 3MF / STL / ZIP      in-memory LRU caches (uploads, traces, models)
```

## Setup (done)
- The project lives in `C:\Users\Hezi\img2print`, a git repo with `origin` at `git@github.com:ZackHirshhorn/img2print.git`.
- Everything is installed in a local venv: `python -m venv .venv`, then `.venv\Scripts\python -m pip install -e ".[web,dev]"`. `.venv/` is in `.gitignore`.
- MIT license (`LICENSE`, `license = "MIT"` in `pyproject.toml`, which needs setuptools>=77).

## Done

### Step 1: shared settings and pipeline (in `src/img2print/`)
- `settings.py`, the `Settings` dataclass:
  - It holds every option the CLI has, plus `recipe` (only `"tile"` for now).
  - `page` counts from 1.
  - `validate()` runs in `__post_init__`, so a bad value raises a `ValueError` with a readable message. Pydantic/FastAPI turns that into a 422.
  - It has `to_dict`/`from_dict` (unknown keys are rejected), `to_json`/`from_json` and `save`/`load`.
  - Helpers: `color_mode` (true when `colors` or `palette` is set), `size()` (tracing kwargs, with the page from 0) and `tile_options()`.
- `pipeline.py`:
  - `trace_layers(source, settings)` returns `list[Artwork]`, background first, each with `.color` set. In 2-colour mode it returns `[paper, ink]`, where paper is the frame minus the ink.
  - `build_model(layers, settings)` returns a `Model`.
  - `build()` does both.
- `model.py`:
  - New `DENSITY` (PLA, PETG, ABS, TPU) and `FILAMENT_DIAMETER = 1.75`.
  - New `Model.to_glb()`.
  - New `Model.stats(material)`: per part, name, colour, triangles, watertight, volume, grams and metres.
  - `summary()` now formats `stats()`, with the same output as before.
- `cli.py`:
  - It now goes through `pipeline`.
  - It uses `argument_default=SUPPRESS`, so only flags actually given override a `--settings file.json`. A size flag clears the size from the file.
  - New flags `--settings` and `--save-settings`.
  - It prints a filament estimate.
  - Checked: STL volumes are identical to `image_to_tile(...)` for the pizza logo at 120 mm raised.

### Step 2: FastAPI backend (in `src/img2print/web/`)
- `cache.py`: a thread-safe LRU with a byte budget and a TTL.
- `schemas.py`: pydantic request and response models. `Settings` is the library dataclass itself, so there is one definition.
- `api.py`: the routes, all under `/api`.
  - `GET /info`: version, whether PDF is available, materials, upload limit.
  - `GET /health`
  - `POST /uploads` (multipart `file`):
    - Returns `{id (sha256), filename, kind raster|svg|pdf, width, height, pages, colors[{color, name, share}]}`.
    - Swatches under 1% are hidden as anti-aliasing shades.
  - `POST /trace` `{upload_id, settings}`:
    - Returns `{width, height, layers[{name, color, area, path}]}`.
    - `path` is SVG path data in mm, with y down; fill it with the even-odd rule.
    - Traces are cached and keyed without the plate-only options (base, layer, thickness, base_color, corner_radius, raised, stacking), so a rebuild after changing only those skips tracing.
  - `POST /models` `{upload_id, settings, material}`:
    - Returns `{id, size, material, parts[{…stats, stl_url}], trace, glb_url, threemf_url, zip_url}`.
    - Limits: at most 2 builds at once, with a 120 s timeout.
  - `GET /models/{id}/preview.glb`, `/model.3mf`, `/parts/{name}.stl` and `/bundle.zip`:
    - Each file is made on first request and kept.
    - Downloads send `Content-Disposition` with `filename*=UTF-8''…`, so Hebrew names work.
  - Errors: `ValueError`/`ImportError` give 422 with the library's message, a decompression bomb gives 413, the timeout gives 504, and an expired id gives 404.
  - Limits: 25 MB upload and `Image.MAX_IMAGE_PIXELS = 40M`.
- `server.py`:
  - `create_app()` serves the API, plus the SPA from `web/static/`. Hashed `assets/` files are cached immutably, and other paths fall back to `index.html`. If the frontend isn't built, a short help page appears instead.
  - `main()` is the `img2print-web` command, with `--host` (default 127.0.0.1), `--port 8000`, `--open`, and `--openapi FILE` to write the schema for TS type generation.
- `pyproject.toml`: added the `web` extra (fastapi, uvicorn[standard], python-multipart, pydantic>=2), web dependencies plus httpx in `dev`, the `img2print-web` script, package data `img2print.web: static/**/*`, and pytest `pythonpath = ["src"]`.
- Smoke-tested by hand with TestClient on `../נפוליטנה.png`. Every endpoint works, in both 2-colour and `colors: 3` modes.

### Step 2b: backend tests (`tests/test_web.py`, 24 tests, FastAPI `TestClient`)
- Info/health; PNG, SVG and PDF uploads (kind, size, swatches); empty, unreadable and oversized uploads (422/413).
- Trace in 2-colour and colour modes, with areas matching `trace_image`/`trace_colors`; a trace is reused when only plate options change.
- Bad settings give a 422 with the library's message; unknown upload/model/part ids give 404; an unknown material gives 422.
- A blank image traces (empty ink layer) but building it gives 422.
- Build in both modes, then GLB/3MF/STL/ZIP downloads parse back with `trimesh`, watertight, with STL volumes matching the stats.
- A Hebrew file name round-trips through `filename*=UTF-8''…`.
- `Settings` JSON round trip, unknown keys and validation; `Cache` LRU eviction and TTL; the CLI's `--settings`/`--save-settings` override behaviour.
- Note: `MAX_UPLOAD_MB` must stay an integer, because it is passed to `UploadFile.read()`.

### Step 3: frontend MVP (`web/`), first version
- Built as planned below: `package.json` with exact pins, `vite.config.ts`, generated `src/api/schema.d.ts`, `src/api/client.ts`, `src/store.ts`, and the components `Dropzone`, `SettingsPanel`, `Results` and `Preview3D` (plus shared controls in `fields.tsx`), `App.tsx`, `index.html` and `styles.css`.
- `web/.npmrc` keeps npm's cache in `web/.npm-cache`. npm 11 blocks esbuild's postinstall script; it isn't needed, because the binary comes from `@esbuild/win32-x64`.
- `gen:api` needs `img2print-web` on PATH, so activate `.venv` first.
- The palette is a comma-separated text field for now; Step 4's PaletteEditor replaces it. A material change rebuilds the current model so the grams update.
- The base colour is a text field, so it is also replaced by the PaletteEditor.
- Checked: `npm run build` (including `tsc --noEmit`) is clean, and a live `img2print-web` serves the SPA, its assets and the full API flow. **Not yet checked in a real browser:** the 3D view, dark mode and the narrow layout.
- `.gitignore`: already has `web/node_modules/`, `web/.npm-cache/`, `web/openapi.json` and `src/img2print/web/static/`.

## Remaining

### Step 3 (reference): frontend MVP (`web/`, Vite + React 18 + TS)
- Pin exact versions in `package.json`, for example react 18.3.1, three 0.169, @react-three/fiber 8.17, @react-three/drei 9.114, @tanstack/react-query 5.59, zustand 4.5, vite 5.4, @vitejs/plugin-react 4.3, typescript 5.6 and openapi-typescript 7.4.
- `vite.config.ts`: dev proxy `/api` to `http://127.0.0.1:8000`, with `build.outDir = "../src/img2print/web/static"` and `emptyOutDir: true`.
- Types: the npm script `gen:api` runs `img2print-web --openapi openapi.json && openapi-typescript openapi.json -o src/api/schema.d.ts`. Then `src/api/client.ts` wraps the fetch calls and normalises errors: `detail` can be a string or a list of `{msg}`, and the "Value error, " prefix is stripped.
- `src/store.ts` (zustand, with `persist` for the settings): settings, the upload, the trace, the built model, the material, and UI state (hidden parts, explode, auto-build).
- Components:
  - **Dropzone**: drag-drop, paste or browse. Shows a thumbnail through an object URL, a PDF page picker when `pages > 1`, and the file name with `dir="auto"`.
  - **SettingsPanel**:
    - Size: a width/height/longest switch plus mm, and padding (a blank border inside that size).
    - Colours: a count or a palette, and the background colour. There is no separate black-and-white mode: 2 colours covers it.
    - Style: how the colours are stacked, then corner radius. "Full depth" (each colour runs the whole plaque thickness), "Top only" (a plain base in a chosen filament, the whole design in the top layer; the default) or "By layers". No printer presets or face-down: those belong to the slicer. "Raised" is library and CLI only.
    - "By layers" means **colour by layer**, exactly as on a single-nozzle printer without an automatic colour changer, where every layer of the print is one colour and the user pauses to swap filament between layers. So: a base in the background colour from the bed up to "Base"; then each other colour in its own band, "Each colour's layer" thick, right above the previous one, so every colour ends at a different height and no layer holds two filaments. A colour's band also runs under every later colour to hold it up, so from above each area shows its own colour. On a shape, the bands stand out of the face; print it face up. The server builds this from `stacking: "layers"` whatever `raised` says, and the build response lists `filament_changes` (height, colour), which the results panel shows as the pause heights. Tested by `test_by_layers_is_colour_by_layer` (API, from the STL files) and the `test_colour_by_layer_*` library tests.
    - Colour: a count, or a palette.
    - Advanced: smooth, min_area, simplify.
  - **Results**:
    - Size; per part, colour, volume, grams and metres; totals; and a warning when a part is not watertight.
    - A material select.
    - Download links for the 3MF, each STL and the ZIP.
  - **Preview3D**:
    - `useLoader(GLTFLoader, glb_url)`, with the parts matched by node name to set a `MeshStandardMaterial` in each part's colour.
    - Trimesh is Z-up, so the model group is rotated −90° about X and centred on a grid build plate.
    - OrbitControls, a show/hide toggle per part, and an exploded-view slider that offsets part *i* up by *i*×explode.
  - The **Build** button builds the model, with an auto-build toggle.
- `index.html` and `styles.css`:
  - Colour tokens on `:root`, with dark mode through `prefers-color-scheme`.
  - Three panes (settings | preview tabs | results) that stack on narrow screens.

### Step 4: polish
- **Preview2D**: an SVG with `viewBox="0 0 w h"`. Behind it, the original (an `<image>` with `preserveAspectRatio="none"`, raster and SVG only) with an opacity slider. On top, the layer paths with `fill-rule="evenodd"`, which can be toggled. Wheel zoom and drag pan through the viewBox. Live updates from `/api/trace` through react-query, keyed on (upload id, settings), with a 300 ms debounce and `placeholderData: keepPreviousData`.
- **PaletteEditor**: swatches seeded from `upload.colors`. You can edit (colour input), delete, add and reorder them, and pick the background. Its output is `settings.palette` and `settings.background`.
- **Settings file**: save the settings as JSON (Blob download) and load them back (file input). This is the same format as the CLI's `--settings`.
- Show the error and the 504 "too long" messages inline.

### Step 5: packaging and deployment
- `Dockerfile`, multi-stage:
  1. `node:22-slim` runs `npm ci && npm run build`.
  2. `python:3.12-slim` does `pip install .[web]`, plus `pymupdf` behind `ARG WITH_PDF=0`. PyMuPDF is AGPL, which matters when hosting publicly.
  3. `CMD uvicorn img2print.web.server:app --host 0.0.0.0 --port 8000`.
- `.gitignore`: add `web/node_modules/`, `web/openapi.json` and `src/img2print/web/static/`.
- README: a "Web app" section covering:
  - Running it: `pip install -e .[web]`, `cd web && npm ci && npm run build`, then `img2print-web --open`.
  - Development: `img2print-web` in one terminal and `npm run dev` in another.
  - Docker.
- Update `todo.md`: mark "preview", "settings as one file" and "filament estimates" as done.

### Step 6: later, from `todo.md`
- New recipes (keychain, coaster or magnet, lithophane, cookie cutter): add each to `settings.RECIPES` and `pipeline.build_model`. The UI's "Product" dropdown reads them from `/api/info`, so add a `recipes` field there.
- A printability overlay on the 2D preview that marks strokes thinner than the nozzle (0.4 mm) in red. It matters for the fine Hebrew line in the logo.
- Batch upload.

## Verification
- `pytest`: the existing 38 tests plus `test_web.py`.
- The CLI still behaves the same: `img2print ../נפוליטנה.png --width 120 --raised` gives white ≈17176 mm³ and black ≈994 mm³.
- Manual end-to-end:
  1. Run `img2print-web --open` and drop in `נפוליטנה.png`.
  2. Move the threshold and watch the 2D preview update.
  3. Build, then orbit the 3D view and toggle the parts.
  4. Download the 3MF and open it in Bambu, Orca or Prusa: one object with two coloured parts.
  5. Repeat with colour mode (3 colours) and with an SVG.
- Frontend: `npm run build` and `tsc --noEmit` are clean.
- Docker: `docker build .`, then `docker run -p 8000:8000`, then the same browser smoke test.
