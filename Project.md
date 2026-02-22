# Manim Composer — Project Documentation

## What It Is

A visual editor for creating [ManimGL](https://github.com/3b1b/manim) animations. Place LaTeX equations on a canvas, edit properties, add animations, generate valid ManimGL Python code, and preview in a live GL window.

**Target engine**: ManimGL (3b1b/manim) — the OpenGL version. Not Manim Community.

## Current State (MVP)

Working end-to-end flow:

1. App launches with a default `F=ma` equation on a black canvas
2. Click MathTex tool + click canvas to place new equations
3. Select an item to edit its LaTeX, color, and position in the Properties panel
4. Add animations (Write, FadeIn, etc.) via the Animation panel
5. Switch to the Code tab to see the generated ManimGL script
6. Click Preview to render the scene in ManimGL's OpenGL window
7. Export to `.py` for standalone use

## Tech Stack

| Component       | Technology                                     |
|-----------------|-------------------------------------------------|
| Language        | Python 3.13+                                    |
| GUI Framework   | PyQt6 with `.ui` files (Qt Designer)            |
| Rendering       | ManimGL v1.7+ (3b1b/manim, OpenGL)              |
| Math            | NumPy                                            |
| Package Manager | uv (with hatchling build backend)               |
| LaTeX           | Bundled TinyTeX (auto-installed to `%LOCALAPPDATA%/ManimComposer/TinyTeX/`) |
| SVG Conversion  | pymupdf (`latex → DVI → dvipdfmx → PDF → pymupdf → SVG`)                  |

## Running

```bash
uv sync
uv run manim-composer
```

Do **not** run `python main.py` directly — the entry point is a uv-managed script.

## Project Structure

```
ManimStudio/
├── pyproject.toml                          # Project config, dependencies, entry point
├── Project.md                              # This file
├── README.md                               # Short overview
├── TODO.md                                 # Future ideas
├── GEMINI.md                               # AI context doc
│
└── manim_composer/
    ├── main.py                             # Entry point, QMainWindow, canvas setup, preview
    ├── main_window.ui                      # Qt Designer layout (all panels, toolbars, tabs)
    ├── patches.py                          # ManimGL monkey-patches for MiKTeX compatibility
    ├── PLAN.md                             # Full 8-phase implementation roadmap
    │
    ├── models/
    │   └── scene_state.py                  # TrackedObject, AnimationEntry, SceneState
    │
    ├── views/
    │   └── canvas_items/
    │       └── mathtex_item.py             # LaTeX → PNG rendering for the canvas
    │
    ├── controllers/
    │   └── properties_controller.py        # Properties panel ↔ SceneState wiring
    │
    ├── codegen/
    │   ├── generator.py                    # SceneState → ManimGL Python code
    │   └── parser.py                       # (future: code → SceneState parser)
    │
    ├── latex_manager.py                    # TinyTeX auto-install, detection, PATH mgmt
    │
    ├── preview/                            # (future: live IPC preview)
    └── resources/                          # (future: icons, stylesheets)
```

## Architecture

### Data Flow

```
Canvas (QGraphicsScene)
    ↕  selection/drag events
Properties Panel (PyQt6 widgets)
    ↕  reads/writes
SceneState (pure Python dataclasses)
    ↓  generates
Code Generator → ManimGL Python script
    ↓  subprocess
Preview (manimgl in GL window)
```

### Key Modules

**`models/scene_state.py`** — Central data model (no Qt dependency).
- `TrackedObject`: name, obj_type, latex, color (position read live from QGraphicsItem)
- `AnimationEntry`: target_name, anim_type, duration, easing
- `SceneState`: object registry with auto-naming (`eq_1`, `eq_2`...), animation CRUD, reverse lookup

**`codegen/generator.py`** — Generates complete ManimGL scripts.
- Uses `Tex(r"...")` (ManimGL), not `MathTex` (Community)
- Reads positions live from canvas items, converts pixel coords to Manim units
- `interactive=True` appends `self.embed()` for preview mode

**`controllers/properties_controller.py`** — Wires the Properties panel to SceneState.
- Selection-driven: shows properties when an item is selected
- LaTeX editing with 500ms debounce (re-renders on pause, not every keystroke)
- Color picker via QColorDialog
- Position spinners with coordinate conversion (pixel/100, Y flipped)
- `_updating` flag prevents signal feedback loops

**`patches.py`** — ManimGL monkey-patches for MiKTeX compatibility.
- MiKTeX's `latex` rejects `-no-pdf` (xelatex-only flag)
- ManimGL passes `-no-pdf` unconditionally to all compilers
- Patch: only pass `-no-pdf` when compiler is `xelatex`

**`latex_manager.py`** — TinyTeX auto-installation and PATH management.
- Downloads TinyTeX-0 (~45 MB) from yihui.org and extracts to `%LOCALAPPDATA%/ManimComposer/TinyTeX/`
- Installs required TeX Live packages via `tlmgr` (latex-bin, dvipng, dvipdfmx, amsmath, amsfonts, etc.)
- `detect()` checks TinyTeX first, then system LaTeX
- `get_latex_env()` always returns env dict with TinyTeX on PATH
- `offer_install()` / `run_install()` — Qt UI for one-click install with progress dialog

**`main.py`** — Application entry point and main window.
- Loads `.ui` file via `uic.loadUi()`
- Sets up canvas, toolbar, tabs, event filters
- Preview uses a launcher script that patches manimgl before running
- Export to `.py` for standalone scripts

## Coordinate System

| Space          | X Range     | Y Range     |
|----------------|-------------|-------------|
| Canvas (px)    | -700 to 700 | -400 to 400 |
| Manim (units)  | -7 to 7     | -4 to 4     |

Conversion: `manim_x = pixel_x / 100`, `manim_y = -pixel_y / 100` (Y is flipped).

## Platform Compatibility Notes

### Python 3.13
- `audioop` removed from stdlib — requires `audioop-lts` package
- `pkg_resources` removed from setuptools v82 — pin `setuptools<81`

### dvisvgm Crash on Windows (CreateProcessW Incompatibility)

**Problem**: `dvisvgm` crashes when called from Python's `subprocess.run()` on Windows.
The crash happens during DVI processing (after "pre-processing DVI file"), not at startup.
Manim CE uses dvisvgm for DVI→SVG conversion, so this breaks all LaTeX rendering.

**Root cause**: Python's `subprocess.run()` uses `CreateProcessW` on Windows. TeX Live
and standalone dvisvgm builds (MinGW/GCC) are incompatible with `CreateProcessW`'s DLL
resolution. MiKTeX's MSVC-built dvisvgm partially works (with `shell=True` or `cwd` set
to exe dir), but TeX Live builds crash with ALL invocation methods from Python.

| Build      | subprocess.run | shell=True | cmd /c | cwd=exe_dir | os.system | bash |
|------------|:-:|:-:|:-:|:-:|:-:|:-:|
| MiKTeX     | crash | OK | OK | OK | OK | OK |
| TinyTeX    | crash | crash | crash | crash | crash | OK* |
| Standalone | crash | crash | crash | crash | crash | OK* |

*Only works from Git Bash (MSYS2 layer), not from Python-spawned bash.

**Exit codes**: TeX Live → -2 (0xFFFFFFFE), MiKTeX/Standalone → -4 (0xFFFFFFFC).

**Solution**: Replaced dvisvgm entirely with a pymupdf-based pipeline:
```
latex → DVI → dvipdfmx → PDF → pymupdf.get_svg_image() → SVG
```
This is implemented as a monkey-patch (`_SVG_PATCH`) prepended to the render script.
The pymupdf pipeline is ~0.5s per render, fully self-contained (no external binary for
SVG conversion), and works on any Windows machine.

**Caveat**: pymupdf SVG output lacks dvisvgm-specific `<g id='uniqueNNN'>` tags.
Manim CE logs a warning ("Using fallback to root group") but renders correctly.
Multi-part TeX expressions may not isolate individual parts for animation.

### MiKTeX on Windows
- `latex` command rejects `-no-pdf` flag (only valid for xelatex)
- ManimGL unconditionally passes `-no-pdf` → crashes on MiKTeX
- Fix: monkey-patch `full_tex_to_svg` in `manimlib.utils.tex_file_writing`
- Preview subprocess uses a launcher script that applies the patch before importing manimgl

### ManimGL vs Manim Community
- ManimGL: `Tex` for math, `TexText` for text, `from manimlib import *`
- Community: `MathTex` for math, `Text` for text, `from manim import *`
- This project targets **ManimGL only**

### TinyTeX Installation Notes
- TinyTeX-0 is a minimal bundle — it does NOT include `latex.exe` out of the box
- `latex-bin` must be explicitly installed via `tlmgr`
- TeX Live has no `amssymb` package — use `amsfonts` (includes amssymb + CM fonts)
- `babel-english` is needed for Manim CE's default tex template
- GitHub CDN blocks `urlretrieve` without a `User-Agent` header (403) — use `Request` + `urlopen`

## Dependencies

Defined in `pyproject.toml`:
```
manimgl>=1.7.0
manim>=0.18             # Manim Community Edition (for CE render mode)
pymupdf>=1.25           # PDF→SVG conversion (replaces dvisvgm)
numpy>=2.4.2
pyqt6>=6.10.2
audioop-lts             # Python 3.13 compat
setuptools<81           # pkg_resources compat
```

Build system: hatchling (required for uv entry point installation).

System: No external dependencies required. TinyTeX is auto-installed on first launch.
