# Manim Composer — Project Documentation

## What It Is

A PowerPoint-style visual editor for creating [ManimGL](https://github.com/3b1b/manim) animations. Place LaTeX equations on a canvas, edit properties, add animations, generate valid ManimGL Python code, and preview in a live GL window.

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
| LaTeX           | MiKTeX or TeX Live (latex + dvipng for canvas, latex + dvisvgm for manimgl) |

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
    │   └── generator.py                    # SceneState → ManimGL Python code
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

**`patches.py`** — ManimGL monkey-patches for MiKTeX.
- MiKTeX's `latex` rejects `-no-pdf` (xelatex-only flag)
- ManimGL passes `-no-pdf` unconditionally to all compilers
- Patch: only pass `-no-pdf` when compiler is `xelatex`

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

### MiKTeX on Windows
- `latex` command rejects `-no-pdf` flag (only valid for xelatex)
- ManimGL unconditionally passes `-no-pdf` → crashes on MiKTeX
- Fix: monkey-patch `full_tex_to_svg` in `manimlib.utils.tex_file_writing`
- Preview subprocess uses a launcher script that applies the patch before importing manimgl

### ManimGL vs Manim Community
- ManimGL: `Tex` for math, `TexText` for text, `from manimlib import *`
- Community: `MathTex` for math, `Text` for text, `from manim import *`
- This project targets **ManimGL only**

## Dependencies

Defined in `pyproject.toml`:
```
manimgl>=1.7.0
numpy>=2.4.2
pyqt6>=6.10.2
audioop-lts          # Python 3.13 compat
setuptools<81        # pkg_resources compat
```

Build system: hatchling (required for uv entry point installation).

System: LaTeX distribution (MiKTeX or TeX Live) with `latex`, `dvipng`, and `dvisvgm`.
