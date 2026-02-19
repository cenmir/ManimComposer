# Manim Composer — Implementation Plan

## Context

We are building a **PowerPoint-style visual editor** for creating ManimGL animations. The user wants to visually compose scenes by placing and manipulating graphical objects on a canvas, define animations between them, and have the tool automatically generate valid ManimGL Python code. The target rendering engine is **Grant Sanderson's ManimGL** (`3b1b/manim`), which uses OpenGL for real-time rendering.

The project directory is `c:\Users\mirza\Dropbox\Notes\Manim` — currently empty except for a workflow analysis document.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  File Menu Bar  │  Toolbar Selector (Design | Animation)│
├─────────────────────────────────────────────────────────┤
│        Context-Sensitive Toolbar (ribbon area)          │
├────────────┬────────────────────────────┬───────────────┤
│  Scenes    │                            │               │
│  Panel     │   Canvas / Code Pane       │   Properties  │
│  (thumbs)  │   (tab-switchable)         │   Panel       │
│            │                            │   (right-click│
├────────────┤                            │    editing)   │
│ Animation  │                            │               │
│ Panel      │                            │               │
│ (list)     │                            │               │
├────────────┴────────────────────────────┴───────────────┤
│  Live Preview Window (ManimGL OpenGL — separate window) │
└─────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
manim_composer/
├── main.py                     # Entry point
├── app.py                      # QApplication setup
├── requirements.txt            # Dependencies
│
├── models/                     # Data model (no Qt dependency)
│   ├── __init__.py
│   ├── project.py              # Project: list of SceneModel
│   ├── scene_model.py          # SceneModel: objects + animations
│   ├── mobject_model.py        # MobjectModel: type, position, properties
│   └── animation_model.py      # AnimationModel: type, target, duration, easing
│
├── views/                      # PyQt6 UI components
│   ├── __init__.py
│   ├── main_window.py          # QMainWindow — assembles all panels
│   ├── canvas_widget.py        # Visual canvas (QGraphicsView/QGraphicsScene)
│   ├── code_editor.py          # Syntax-highlighted code pane (QPlainTextEdit)
│   ├── scenes_panel.py         # Left panel — scene thumbnails
│   ├── animation_panel.py      # Left panel — animation list
│   ├── properties_panel.py     # Right panel — object property editor
│   ├── toolbar_manager.py      # Toolbar selector + context-sensitive toolbars
│   └── canvas_items/           # QGraphicsItem subclasses for each object type
│       ├── __init__.py
│       ├── base_item.py        # Selectable, draggable, right-clickable base
│       ├── mathtex_item.py     # LaTeX equation rendered as pixmap
│       ├── text_item.py        # Plain text
│       ├── circle_item.py      # Circle shape
│       ├── rectangle_item.py   # Rectangle shape
│       └── arrow_item.py       # Arrow shape
│
├── controllers/                # Business logic connecting models and views
│   ├── __init__.py
│   ├── editor_controller.py    # Main controller — coordinates everything
│   ├── canvas_controller.py    # Handles canvas interactions → model updates
│   └── preview_controller.py   # Coordinates UI actions with preview/renderer.py
│
├── codegen/                    # ManimGL code generation
│   ├── __init__.py
│   ├── generator.py            # Model → ManimGL Python code
│   └── parser.py               # ManimGL Python code → Model (future, for code edits)
│
├── preview/                    # Live preview integration (3b1b-style)
│   ├── __init__.py
│   ├── interactive_wrapper.py  # Runs INSIDE ManimGL process: stdin commands, checkpoint/restore
│   ├── renderer.py             # Studio-side controller: spawns subprocess, sends JSON commands
│   └── protocol.py             # Shared command/response definitions
│
└── resources/                  # Icons, stylesheets
    ├── icons/
    └── style.qss
```

---

## Core Data Model

### MobjectModel (`models/mobject_model.py`)
```python
@dataclass
class MobjectModel:
    id: str                    # UUID
    type: MobjectType          # Enum: MATHTEX, TEXT, CIRCLE, RECTANGLE, ARROW, LINE
    position: tuple[float, float]  # (x, y) in Manim coordinate space
    properties: dict           # Type-specific: {"latex": "E=mc^2"}, {"text": "Hello"}, {"radius": 1.0}, etc.
    z_index: int
    name: str                  # Variable name in generated code, e.g. "eq_1"
```

### AnimationModel (`models/animation_model.py`)
```python
@dataclass
class AnimationModel:
    id: str
    type: AnimationType        # Enum: FADE_IN, WRITE, SHOW_CREATION, TRANSFORM, FADE_OUT
    target_id: str             # MobjectModel.id this animation applies to
    duration: float            # run_time in seconds
    params: dict               # Extra params: {"shift": "UP"}, {"rate_func": "smooth"}
    order: int                 # Execution order within the scene
```

### SceneModel (`models/scene_model.py`)
```python
@dataclass
class SceneModel:
    id: str
    name: str                  # Class name, e.g. "Scene1"
    mobjects: list[MobjectModel]
    animations: list[AnimationModel]
    order: int                 # Position in project
```

### Project (`models/project.py`)
```python
@dataclass
class Project:
    version: str = "1.0"
    name: str
    scenes: list[SceneModel]

    def save(self, path: str)          # Serialize to JSON, write as .manim file
    def load(cls, path: str) -> Project  # Read .manim file, deserialize from JSON
    def to_dict(self) -> dict
    def from_dict(cls, d) -> Project
```
**File format**: `.manim` — a JSON file with the project data. Human-readable, git-friendly.

---

## Key Components

### 1. Canvas (`views/canvas_widget.py`)

Uses **QGraphicsView + QGraphicsScene** — Qt's scene graph framework which provides:
- Built-in item selection, dragging, z-ordering
- Coordinate transforms between screen and scene space
- Efficient rendering of many items

**Coordinate mapping**: Manim uses a coordinate system centered at origin with roughly [-7, 7] x [-4, 4] visible range. The canvas maps this to the QGraphicsScene coordinate space.

**Canvas items** (`views/canvas_items/`): Each item subclasses `QGraphicsItem`:
- `base_item.py`: Provides selection handles, drag behavior, right-click context menu
- `mathtex_item.py`: Runs `latex` → `dvisvgm` to render LaTeX to SVG, displays as QGraphicsSvgItem. Falls back to a placeholder if LaTeX not installed.
- Shape items: Use QPainterPath for circles, rectangles, arrows

**Interactions**:
- **Tool mode**: When a tool is active (e.g., "Add MathTex"), clicking the canvas creates a new object at that position
- **Select mode**: Click to select, drag to move, multi-select with rubber band
- **Right-click**: Opens context menu → "Edit Properties" launches the properties panel

### 2. Code Editor (`views/code_editor.py`)

- `QPlainTextEdit` with Python syntax highlighting (`QSyntaxHighlighter` subclass)
- Tab-switchable with the canvas (using `QStackedWidget`)
- **Canvas → Code**: Whenever the model changes, regenerate code and update editor
- **Code → Canvas**: A "Sync to Canvas" button parses edited code back (Phase 2 stretch goal — initially read-only or one-way)

### 3. Scenes Panel (`views/scenes_panel.py`)

- `QListWidget` with thumbnail icons (rendered from canvas miniatures)
- Add/delete/reorder via buttons and drag-drop
- Clicking a scene switches the canvas and animation panel to that scene's content
- Thumbnails update on scene changes (throttled, using QGraphicsScene.render() to a QPixmap)

### 4. Animation Panel (`views/animation_panel.py`)

- `QListWidget` showing animations in order: "1. FadeIn — eq_1 (1.0s)"
- Drag to reorder
- Click to select → properties appear in the Properties Panel
- Toolbar buttons: Add Animation, Delete, Move Up/Down
- "Add Animation" shows a dialog: pick target object, animation type, duration

### 5. Properties Panel (`views/properties_panel.py`)

- `QStackedWidget` that shows different forms depending on what's selected:
  - **MathTex selected**: LaTeX code input, font size, color picker
  - **Shape selected**: Dimensions, stroke/fill color, stroke width
  - **Animation selected**: Type dropdown, duration spinner, easing dropdown
- Changes immediately update the model and canvas

### 6. Toolbar System (`views/toolbar_manager.py`)

- **Toolbar Selector**: `QTabBar` at the top with tabs: "Design", "Animation"
- **Design Toolbar**: Object tool buttons (Select, MathTex, Text, Circle, Rectangle, Arrow, Line), color picker, alignment buttons
- **Animation Toolbar**: "Add Animation" button, animation type dropdown, duration spinner, "Preview Scene" button
- Switching tabs swaps the visible toolbar (using `QStackedWidget`)

### 7. Live Preview (`preview/`) — 3b1b-Style Persistent Preview

**Strategy: Persistent subprocess with checkpoint/restore (inspired by 3b1b's `checkpoint_paste` workflow)**

The key insight from Grant Sanderson's workflow: **the OpenGL window never closes**. Instead of killing and restarting a process on every edit, we keep a single ManimGL process alive and communicate with it via IPC to revert state and replay changed animations instantly.

#### How 3b1b's `checkpoint_paste` works (reference)
1. ManimGL starts with `embed()` → drops into IPython with live `self` (Scene) access
2. `checkpoint_paste()` reads code from clipboard, keys state snapshots by the first comment line
3. First run of a comment key → saves deep copy of scene state → executes code
4. Subsequent runs of same key → **reverts to saved snapshot** → executes modified code
5. Result: instant replay without window restart

#### Our adaptation for Manim Composer

We replace the clipboard+IPython mechanism with a structured IPC channel:

```
┌──────────────┐    JSON over stdin     ┌──────────────────────┐
│ Manim Composer │ ──────────────────────▶│ interactive_wrapper.py│
│  (PyQt6 UI)  │                        │  (inside ManimGL)    │
│              │◀────────────────────── │                      │
│  renderer.py │    JSON over stdout    │  checkpoint/restore  │
└──────────────┘                        │  exec() code blocks  │
                                        │  OpenGL window stays │
                                        └──────────────────────┘
```

**`preview/interactive_wrapper.py`** — runs inside the ManimGL process:
- Starts ManimGL scene, enters interactive loop reading JSON commands from stdin
- Maintains a dict of **checkpoints**: `{checkpoint_id: deep_copy_of_scene_state}`
- On `checkpoint` command → saves current mobjects, camera state, etc.
- On `restore` command → reverts scene to saved checkpoint (clears current mobjects, restores copies)
- On `run_code` command → `exec()`s a code snippet with access to `self` (the Scene)
- On `load_scene` command → initializes scene from full generated code

**`preview/renderer.py`** — Studio-side controller:
- Spawns `interactive_wrapper.py` as a subprocess (once, on first Preview)
- Sends JSON commands via stdin, reads responses from stdout
- Manages the "hot reload" logic: detect which animation changed → send `restore` to the right checkpoint → send updated `run_code`
- Kills and restarts only on catastrophic errors

**Command protocol** (JSON over stdin/stdout):
```json
{"cmd": "load_scene", "code": "class Scene1(Scene):\n  def construct(self):\n    ..."}
{"cmd": "checkpoint", "id": "after_step_2"}
{"cmd": "restore", "id": "after_step_2"}
{"cmd": "run_code", "code": "self.play(Write(eq), run_time=1.5)"}
{"cmd": "shutdown"}
```

**Response protocol**:
```json
{"status": "ok", "cmd": "checkpoint", "id": "after_step_2"}
{"status": "error", "cmd": "run_code", "message": "NameError: name 'eq' is not defined"}
```

**Why this approach:**
- ManimGL's OpenGL window stays open → no flicker, no cold start
- Checkpoint/restore enables instant "undo to known state + replay" (same principle as 3b1b)
- Structured IPC replaces fragile clipboard/IPython mechanism
- Code generation can produce both full scenes AND incremental snippets
- Fallback: if the persistent process dies, renderer.py restarts it transparently

---

## Code Generation Strategy (`codegen/generator.py`)

The generator walks the Project model and produces a valid ManimGL script:

```python
# Auto-generated by Manim Composer
from manimlib import *

class Scene1(Scene):
    def construct(self):
        # Objects
        eq_1 = MathTex(r"E = mc^2")
        eq_1.move_to(np.array([1.5, 2.0, 0]))

        circle_1 = Circle(radius=1.0, color=BLUE)
        circle_1.move_to(np.array([-2.0, 0.0, 0]))

        # Animations
        self.play(Write(eq_1), run_time=1.5)
        self.play(ShowCreation(circle_1), run_time=1.0)
```

**Key mappings**:
- `MobjectType.MATHTEX` → `MathTex(r"...")`
- `MobjectType.TEXT` → `Text("...")`
- `MobjectType.CIRCLE` → `Circle(radius=..., color=...)`
- `AnimationType.WRITE` → `Write(target)`
- `AnimationType.FADE_IN` → `FadeIn(target)`
- `AnimationType.SHOW_CREATION` → `ShowCreation(target)`
- Position → `.move_to(np.array([x, y, 0]))`

---

## Implementation Phases

### Phase 1: Qt Designer .ui File + Project Skeleton
**Files to create:**
- `manim_composer/main_window.ui` — Qt Designer `.ui` file defining the full layout:
  - QMainWindow with menu bar (File, Edit, View, Help)
  - Toolbar selector (`QTabBar`: Design | Animation) below menu bar
  - Context-sensitive toolbar area (`QStackedWidget` with `QToolBar` per tab)
  - Left dock: Scenes panel (`QListWidget`) + Animation panel (`QListWidget`) in a `QSplitter`
  - Center: `QStackedWidget` with Canvas (`QGraphicsView`) and Code Editor (`QPlainTextEdit`) tabs
  - Right dock: Properties panel (`QStackedWidget` with forms)
  - Status bar
- `main.py` — Entry point, loads `.ui` file and launches app
- `requirements.txt` — PyQt6, manimgl, numpy

**Outcome**: Run `python main.py` → the full window layout appears with all panels, toolbars, and docks visible (no functionality yet, just the UI shell).

### Phase 2: Toolbar + More Object Types
- `views/toolbar_manager.py` — Design toolbar with tool buttons
- `views/canvas_items/mathtex_item.py` — LaTeX rendering (SVG pipeline)
- `views/canvas_items/text_item.py`, `arrow_item.py`
- Tool selection state machine (select mode vs. place mode)

**Outcome**: Click tools in the toolbar, click canvas to place objects, including LaTeX equations.

### Phase 3: Properties Panel + Right-Click Editing
- `views/properties_panel.py` — dynamic property forms
- Right-click context menu on canvas items
- LaTeX editor dialog with preview
- Color picker integration

**Outcome**: Right-click a MathTex object → edit LaTeX → see it re-render on canvas.

### Phase 4: Code Generation + Code Pane
- `codegen/generator.py` — model-to-code generator
- `views/code_editor.py` — syntax-highlighted read/edit pane
- Tab switching between canvas and code
- Auto-regenerate code on model changes

**Outcome**: Placing objects on canvas generates viewable ManimGL code.

### Phase 5: Scenes Panel
- `views/scenes_panel.py` — scene list with thumbnails
- Scene switching, add/delete/reorder
- Project model wired to scene panel
- Thumbnail generation from canvas snapshots

**Outcome**: Multiple scenes like PowerPoint slides, each with its own objects.

### Phase 6: Animation System
- `views/animation_panel.py` — animation list
- Animation model CRUD
- Animation property editing in properties panel
- Code generation includes animations
- `views/toolbar_manager.py` — Animation toolbar tab

**Outcome**: Define FadeIn, Write, etc. for objects. Animations appear in generated code.

### Phase 7: Live Preview (3b1b-Style Persistent)
- `preview/interactive_wrapper.py` — Python script that runs **inside** the ManimGL process:
  - Reads JSON commands from stdin
  - Checkpoint/restore logic: saves/restores deep copies of scene state
  - `exec()`s code blocks dynamically against the live Scene
- `preview/renderer.py` — Studio-side controller:
  - Spawns the ManimGL subprocess (once, keeps it alive)
  - Sends JSON commands (load_scene, checkpoint, restore, run_code)
  - Hot-reload logic: detect changed animation → restore checkpoint → send new code
  - Auto-restart on crash
- `preview/protocol.py` — Shared command/response type definitions
- Updated code generator: ability to produce **snippets** for individual animations, not just full scene files

**Outcome**: Press Preview → ManimGL window opens. Edit an animation property → the changed animation replays instantly in the already-open window (no restart). Same principle as 3b1b's `checkpoint_paste` workflow.

### Phase 8: File I/O (.manim format) + Polish
- **`.manim` file format**: Custom extension that is simply a JSON file containing the serialized Project model
  - File → Save / Save As writes `project.manim` (JSON with pretty-print)
  - File → Open reads `.manim` files and deserializes back to the Project model
  - File association: `.manim` files are JSON internally, human-readable, and version-controllable
- Export to standalone `.py` script (ManimGL code)
- File menu: New, Open (.manim), Save (.manim), Save As, Export to .py, Render to video
- Keyboard shortcuts, undo/redo stack
- UI polish, icons, styling

**`.manim` file structure example:**
```json
{
  "version": "1.0",
  "name": "My Project",
  "scenes": [
    {
      "id": "uuid-...",
      "name": "Scene1",
      "order": 0,
      "mobjects": [
        {
          "id": "uuid-...",
          "type": "MATHTEX",
          "name": "eq_1",
          "position": [1.5, 2.0],
          "z_index": 0,
          "properties": {"latex": "E = mc^2", "color": "#FFFFFF", "font_size": 48}
        }
      ],
      "animations": [
        {
          "id": "uuid-...",
          "type": "WRITE",
          "target_id": "uuid-...",
          "duration": 1.5,
          "order": 0,
          "params": {}
        }
      ]
    }
  ]
}
```

**Outcome**: Complete, saveable (`.manim`), exportable Manim Composer.

---

## Dependencies

```
# requirements.txt
PyQt6>=6.6.0
PyQt6-QScintilla>=2.14.0      # Optional: advanced code editor (alternative to plain QPlainTextEdit)
manimgl>=1.7.0                  # 3b1b's ManimGL
numpy>=1.24.0
```

System requirements: LaTeX distribution (MiKTeX or TeX Live) for MathTex rendering, both on the canvas side (SVG generation) and for ManimGL.

---

## Verification Plan

1. **Phase 1 test**: Run `python main.py` → window appears → click canvas → rectangle appears → drag it
2. **Phase 2 test**: Select MathTex tool → click canvas → LaTeX placeholder appears → select Design toolbar tools
3. **Phase 3 test**: Right-click an object → properties panel opens → edit LaTeX → re-renders
4. **Phase 4 test**: Place objects → switch to Code tab → valid ManimGL code displayed
5. **Phase 5 test**: Create 3 scenes → switch between them → each has its own objects
6. **Phase 6 test**: Add animations to objects → they appear in animation panel → code includes `self.play()`
7. **Phase 7 test**: Click Preview → ManimGL window opens → animation plays → edit duration in Studio → animation replays instantly in same window (no restart)
8. **Phase 8 test**: Save project → close → reopen → all scenes/objects/animations restored
