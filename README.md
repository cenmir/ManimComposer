# Manim Composer

A PowerPoint-style visual editor for creating [ManimGL](https://github.com/3b1b/manim) animations. Design scenes by placing and manipulating objects on a canvas, define animations, and export valid ManimGL Python code.

## Features (Phase 1 — Current)

- **Visual canvas** with black background matching ManimGL's coordinate system
- **LaTeX rendering** via `latex` + `dvipng` pipeline (falls back to styled text if LaTeX is not installed)
- **Tool-based object placement** — select MathTex tool, click canvas to place
- **Qt Designer layout** — toolbar tabs (Design / Animation), scenes panel, animations panel, properties panel, code editor pane
- **Drag & drop** — items are selectable and movable on canvas

## Planned

See [manim_composer/PLAN.md](manim_composer/PLAN.md) for the full 8-phase roadmap, including:

- Properties panel with right-click editing
- ManimGL code generation
- Multi-scene support with thumbnails
- Animation system (FadeIn, Write, ShowCreation, Transform, etc.)
- **Live preview** with persistent ManimGL subprocess and checkpoint/restore (inspired by 3b1b's `checkpoint_paste` workflow)
- Save/load `.manim` project files

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) for project management
- LaTeX distribution (MiKTeX or TeX Live) for full MathTex rendering (optional — text fallback provided)

## Getting Started

```bash
# Clone the repository
git clone <repo-url>
cd ManimStudio

# Install dependencies and run
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
├── PLAN.md                        # Implementation roadmap
├── views/
│   └── canvas_items/
│       └── mathtex_item.py        # LaTeX → PNG rendering pipeline
├── models/                        # Data model (future)
├── controllers/                   # Business logic (future)
├── codegen/                       # ManimGL code generation (future)
└── preview/                       # Live preview integration (future)
```

## License

TBD
