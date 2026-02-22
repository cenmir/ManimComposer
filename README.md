# Manim Composer

A visual editor for creating [ManimGL](https://github.com/3b1b/manim) animations. Design scenes by placing and manipulating objects on a canvas, define animations, and export valid ManimGL Python code.

## Features

- **Visual canvas** with black background matching ManimGL's coordinate system
- **LaTeX rendering** via `latex` + `dvipng` pipeline (falls back to styled text if LaTeX is not installed)
- **Tool-based object placement** — select MathTex tool, click canvas to place
- **Drag & drop** — items are selectable and movable on canvas
- **Properties panel** — edit LaTeX, color, font size, and position for selected objects
- **Animation system** — add, reorder (drag-drop), and edit animations with target, type, duration, and easing
- **ManimGL code generation** — export valid Python code from your scene
- **Live preview** with embedded console output
- **Copy & paste** canvas objects (Ctrl+C / Ctrl+V)
- **LaTeX manager** — auto-detects system LaTeX or offers to install TinyTeX

## Planned

See [manim_composer/PLAN.md](manim_composer/PLAN.md) for the full roadmap, including:

- Multi-scene support with thumbnails
- Save/load `.manim` project files

## Quick Install (Windows)

Run this in PowerShell — it installs everything (uv, Python, dependencies) automatically:

```powershell
irm https://raw.githubusercontent.com/cenmir/ManimComposer/main/install.ps1 | iex
```

LaTeX (TinyTeX) is auto-installed on first launch. No manual setup needed.

## Manual Install

If you prefer to set things up yourself:

```bash
# Prerequisites: Python 3.13+ and uv (https://docs.astral.sh/uv/)
git clone https://github.com/cenmir/ManimComposer.git
cd ManimComposer
uv sync
uv run manim-composer
```

## Tech Stack

- **GUI**: PyQt6 with `.ui` files (Qt Designer)
- **Rendering engine**: ManimGL (3b1b/manim, OpenGL version)
- **Math**: NumPy

## Project Structure

```
manim_composer/
├── main.py                        # Entry point (QMainWindow, canvas setup)
├── main_window.ui                 # Qt Designer layout
├── latex_manager.py               # LaTeX detection and TinyTeX installer
├── PLAN.md                        # Implementation roadmap
├── views/
│   └── canvas_items/
│       └── mathtex_item.py        # LaTeX → PNG rendering pipeline
├── models/
│   └── scene_state.py             # Scene data model (objects, animations)
├── controllers/
│   └── properties_controller.py   # Properties & animation panel logic
├── codegen/
│   └── generator.py               # ManimGL code generation
└── preview/                       # Live preview integration
```

## License

TBD
